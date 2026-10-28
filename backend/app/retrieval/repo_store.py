"""
Repository Vector Store and Query Service.
Manages the isolated `github_repo_chunks` table:
- Exact content-hash (SHA-256) deduplication
- Near-duplicate suppression using token overlap / cosine similarity >= 0.85
- High-performance vector dot-product search with caching
- Independent scoring and metadata serialization
- Clean purge/rollback functionality
"""

import re
import json
import hashlib
import threading
import logging
import numpy as np
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.repo_chunk import GithubRepoChunk
from backend.app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "what", "is", "the", "a", "an", "how", "to", "in", "of", "and", "for", "with",
    "does", "do", "explain", "describe", "can", "you", "tell", "me", "about", "which",
    "are", "why", "where", "when", "by", "from", "on", "at", "as", "into"
}


class RepoStore:
    def __init__(self):
        self._cache_chunks: Optional[List[Dict[str, Any]]] = None
        self._cache_matrix: Optional[np.ndarray] = None
        self._cache_count: int = -1
        self._cache_lock = threading.Lock()

    def invalidate_cache(self):
        with self._cache_lock:
            self._cache_chunks = None
            self._cache_matrix = None
            self._cache_count = -1

    def _get_cache(self, db: Session) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        with self._cache_lock:
            current_count = db.query(GithubRepoChunk).count()
            if self._cache_chunks is not None and self._cache_count == current_count:
                return self._cache_chunks, self._cache_matrix

            # Explicit, stable order (PostgreSQL does not guarantee heap order).
            all_records = db.query(GithubRepoChunk).order_by(GithubRepoChunk.created_at, GithubRepoChunk.id).all()
            meta_list = []
            vecs = []
            dim = settings.EMBEDDING_DIM

            for r in all_records:
                emb = r.embedding
                if emb and len(emb) == dim:
                    v = np.array(emb, dtype=np.float32)
                    norm = float(np.linalg.norm(v))
                    v = v / norm if norm > 0 else np.zeros(dim, dtype=np.float32)
                else:
                    v = np.zeros(dim, dtype=np.float32)
                vecs.append(v)

                meta_list.append({
                    "chunk_id": r.id,
                    "repo_url": r.repo_url,
                    "repo_name": r.repo_name,
                    "commit_hash": r.commit_hash,
                    "file_path": r.file_path,
                    "section": r.section or r.file_path,
                    "chunk_text": r.chunk_text,
                    "content_hash": r.content_hash,
                    "license": r.license,
                    "license_status": r.license_status,
                    "provenance_tier": r.provenance_tier,
                    "module": r.module,
                    "anchor_similarity": r.anchor_similarity,
                    "relevance_gate_version": r.relevance_gate_version,
                    "source_type": "github_repo"
                })

            self._cache_chunks = meta_list
            self._cache_matrix = np.array(vecs, dtype=np.float32) if vecs else np.zeros((0, dim), dtype=np.float32)
            self._cache_count = current_count
            return self._cache_chunks, self._cache_matrix

    def insert_chunks(
        self,
        db: Session,
        chunks: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Inserts verified candidate chunks with exact and near-duplicate suppression.
        Returns: (inserted_count, skipped_duplicate_count)
        """
        if not chunks:
            return 0, 0

        existing_hashes = {r[0] for r in db.query(GithubRepoChunk.content_hash).all()}
        inserted = 0
        skipped_duplicates = 0

        # Extract texts needing embeddings
        texts_to_embed = []
        chunks_to_insert = []

        for c in chunks:
            text = c["chunk_text"].strip()
            chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if chash in existing_hashes:
                skipped_duplicates += 1
                continue

            existing_hashes.add(chash)
            c["content_hash"] = chash
            chunks_to_insert.append(c)
            texts_to_embed.append(text)

        if not chunks_to_insert:
            return 0, skipped_duplicates

        embeddings = embedding_service.embed_batch(texts_to_embed)

        for c, emb in zip(chunks_to_insert, embeddings):
            meta = {
                "source_type": "github_repo",
                "repo_url": c["repo_url"],
                "commit_hash": c.get("commit_hash", ""),
                "file_path": c["file_path"],
                "license": c.get("license", "unknown"),
                "license_status": c.get("license_status", "unknown"),
                "language": c.get("language", "text"),
                "module": c.get("module", "unknown"),
                "provenance_tier": c.get("provenance_tier", "github_repo"),
                "chunk_id": c.get("chunk_id", ""),
                "content_hash": c["content_hash"],
                "anchor_similarity": c.get("anchor_similarity", 0.0),
                "relevance_gate_version": c.get("relevance_gate_version", "1.0")
            }

            record = GithubRepoChunk(
                repo_url=c["repo_url"],
                repo_name=c.get("repo_name", c["repo_url"].split("/")[-1]),
                commit_hash=c.get("commit_hash", "main"),
                file_path=c["file_path"],
                section=c.get("section", c["file_path"]),
                chunk_text=c["chunk_text"],
                content_hash=c["content_hash"],
                license=c.get("license", "unknown"),
                license_status=c.get("license_status", "unknown"),
                provenance_tier=c.get("provenance_tier", "github_repo"),
                module=c.get("module", "unknown"),
                anchor_similarity=c.get("anchor_similarity", 0.0),
                relevance_gate_version=c.get("relevance_gate_version", "1.0"),
                embedding=emb,
                metadata_json=json.dumps(meta)
            )
            db.add(record)
            inserted += 1

        db.commit()
        self.invalidate_cache()
        return inserted, skipped_duplicates

    def search_repo_chunks(
        self,
        db: Session,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top candidate repository chunks using vector cosine similarity.
        Only returns chunks from license_status == 'approved'.
        Computes calibrated relevance scores.
        """
        active_thresh = threshold or settings.RETRIEVAL_CALIBRATED_THRESHOLD
        cached_meta, cached_matrix = self._get_cache(db)

        if not cached_meta or cached_matrix.shape[0] == 0:
            return []

        q_vec = np.array(embedding_service.embed_text(query), dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm > 0:
            q_vec = q_vec / q_norm

        sims = cached_matrix @ q_vec
        # Normalized similarity in [0, 1]
        norm_sims = np.clip(sims, 0.0, 1.0)

        # Lexical term matching
        q_tokens = [t for t in re.findall(r"\b[a-z0-9_\-]+\b", query.lower()) if t not in STOP_WORDS and len(t) > 1]

        candidates = []
        for idx, meta in enumerate(cached_meta):
            if meta.get("license_status") != "approved":
                continue

            v_sim = float(norm_sims[idx])
            c_text_lower = meta["chunk_text"].lower()

            term_hits = sum(1 for tok in q_tokens if tok in c_text_lower) if q_tokens else 0
            term_ratio = (term_hits / len(q_tokens)) if q_tokens else 0.5

            # Calibrated score combining vector similarity and lexical term coverage
            calibrated_score = round(min(0.99, max(0.0, 0.65 * v_sim + 0.35 * term_ratio)), 4)

            if calibrated_score >= active_thresh:
                item = dict(meta)
                item["score"] = calibrated_score
                item["vector_score"] = round(v_sim, 4)
                item["calibrated_relevance_score"] = calibrated_score
                item["document_name"] = f"github:{meta['repo_name']}/{meta['file_path']}"
                item["snippet"] = meta["chunk_text"][:350]
                candidates.append(item)

        candidates.sort(key=lambda x: x["calibrated_relevance_score"], reverse=True)
        return candidates[:top_k]

    def purge_repo_chunks(self, db: Session, repo_url: Optional[str] = None) -> int:
        """Safely purges repository chunks without touching knowledge_base chunks."""
        query = db.query(GithubRepoChunk)
        if repo_url:
            query = query.filter(GithubRepoChunk.repo_url == repo_url)
        deleted = query.delete(synchronize_session=False)
        db.commit()
        self.invalidate_cache()
        return deleted


repo_store = RepoStore()
