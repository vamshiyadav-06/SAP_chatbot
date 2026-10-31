"""
Unified Corpus Service for SAP BRIM.
Provides:
- Document tier lookup and mapping
- Chunk module tagging & filtering
- Exact-string corpus identifier indexing & lookup
- Off-domain document filtering (guarded by config flag EXCLUDE_OFF_DOMAIN_DOCS)
- Safe official document ingestion path (requiring explicit user licence confirmation)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

from sqlalchemy import text

from backend.app.config import settings
from backend.app.security.log_safety import privacy_fingerprint
from backend.app.database import engine
from backend.app.corpus.tier_definitions import DOCUMENT_TIER_MAPPING
from backend.app.corpus.module_tagger import tag_chunk_modules
from backend.app.corpus.identifier_indexer import (
    extract_chunk_identifiers,
    classify_identifier_type,
    assign_identifier_module
)

logger = logging.getLogger(__name__)

CORPUS_INDEX_JSON = Path(__file__).resolve().parent.parent / "corpus" / "corpus_identifier_index.json"


class CorpusService:
    """
    Manages document tiers, modules, technical identifier index,
    and domain exclusion guardrails.
    """

    def __init__(self):
        self._identifier_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def get_document_tier(self, filename: str) -> str:
        """Returns authority tier for a document."""
        if filename in DOCUMENT_TIER_MAPPING:
            return DOCUMENT_TIER_MAPPING[filename]["tier"]
        # Case-insensitive fallback
        for name, meta in DOCUMENT_TIER_MAPPING.items():
            if name.lower() == filename.lower():
                return meta["tier"]
        return "self_authored"

    def is_document_off_domain(self, filename: str) -> bool:
        """Returns True if the document is flagged as off-domain."""
        if filename in DOCUMENT_TIER_MAPPING:
            return bool(DOCUMENT_TIER_MAPPING[filename].get("is_off_domain", False))
        for name, meta in DOCUMENT_TIER_MAPPING.items():
            if name.lower() == filename.lower():
                return bool(meta.get("is_off_domain", False))
        return False

    def get_identifier_index(self) -> Dict[str, Dict[str, Any]]:
        """Loads and caches the exact-string technical identifier index."""
        if self._identifier_cache is not None:
            return self._identifier_cache

        # Try JSON export first
        if CORPUS_INDEX_JSON.exists():
            try:
                with open(CORPUS_INDEX_JSON, "r", encoding="utf-8") as f:
                    self._identifier_cache = json.load(f)
                    return self._identifier_cache
            except Exception as e:
                logger.warning(f"Failed to read identifier index JSON: {e}")

        # Fallback to database table
        index_dict = {}
        try:
            with engine.connect() as conn:
                tbl_check = conn.execute(text("SELECT to_regclass('corpus_identifier_index')")).scalar()
                if tbl_check:
                    rows = conn.execute(text(
                        "SELECT identifier, type, module, tier, chunk_ids, occurrence_count FROM corpus_identifier_index"
                    )).fetchall()
                    for r in rows:
                        index_dict[r[0]] = {
                            "identifier": r[0],
                            "type": r[1],
                            "module": r[2],
                            "tier": r[3],
                            "chunk_ids": json.loads(r[4]),
                            "occurrence_count": r[5]
                        }
        except Exception as e:
            logger.error(f"Failed to load identifier index from PostgreSQL: {e}")

        self._identifier_cache = index_dict
        return self._identifier_cache

    def is_identifier_in_corpus(self, identifier: str) -> bool:
        """
        Checks if exact-string identifier exists in the corpus index.
        No normalization is applied.
        """
        index = self.get_identifier_index()
        return identifier in index

    def get_identifier_details(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieves metadata for an exact-string identifier."""
        index = self.get_identifier_index()
        return index.get(identifier)

    def filter_chunks_by_domain(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters out chunks from off-domain documents when EXCLUDE_OFF_DOMAIN_DOCS is True.
        When EXCLUDE_OFF_DOMAIN_DOCS is False (default), returns all chunks untouched.
        """
        if not getattr(settings, "EXCLUDE_OFF_DOMAIN_DOCS", False):
            return chunks

        filtered = []
        for ch in chunks:
            doc_name = ch.get("document_name") or ch.get("source") or ch.get("document") or ""
            if not self.is_document_off_domain(doc_name):
                filtered.append(ch)
            else:
                logger.debug(f"Excluding off-domain chunk from {doc_name}")
        return filtered

    def ingest_official_document(
        self,
        file_path: Path,
        licence_confirmed: bool = False,
        module_hint: str = ""
    ) -> Dict[str, Any]:
        """
        Ingestion path for new official documents.
        Preserves original page numbers, extracts text, generates embeddings,
        and assigns tier 'official_sap'.
        
        CRITICAL CONSTRAINT: Requires explicit licence confirmation.
        """
        if not licence_confirmed:
            raise PermissionError(
                "Ingestion rejected: licence must be confirmed by user before ingesting official documents."
            )

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Lazy load document service and database session
        from backend.app.services.document_service import document_service
        from backend.app.database import SessionLocal

        db = SessionLocal()
        try:
            logger.info("Ingesting official document with licence confirmed: document_ref=%s", privacy_fingerprint(file_path.name))
            doc = document_service.process_pdf(db, file_path)

            # Record in corpus_document_metadata
            from backend.app.corpus.corpus_builder import UPSERT_DOCUMENT_METADATA, init_corpus_tables
            with engine.begin() as conn:
                init_corpus_tables(conn)
                conn.execute(UPSERT_DOCUMENT_METADATA, {
                    "id": doc.id,
                    "filename": file_path.name,
                    "tier": "official_sap",
                    "is_off_domain": 0,
                    "category": "User-Ingested Official SAP Document",
                    "reason": "Ingested with explicit licence confirmation",
                    "page_count": doc.page_count,
                    "chunk_count": len(doc.chunks),
                })

            return {
                "document_id": doc.id,
                "filename": file_path.name,
                "tier": "official_sap",
                "page_count": doc.page_count,
                "chunk_count": len(doc.chunks),
                "status": "ingested_successfully"
            }
        finally:
            db.close()


corpus_service = CorpusService()
