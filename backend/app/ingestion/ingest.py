import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy.orm import Session

# Ensure project root is on sys.path if invoked directly
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import settings
from backend.app.database import SessionLocal, init_db
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.services.document_service import document_service
from backend.app.services.embedding_service import embedding_service
from backend.app.services.retrieval_service import retrieval_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ingestion")

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


def discover_knowledge_base_files() -> List[Path]:
    """
    Recursively scans the knowledge base directories to find all supported documents.
    Covers both settings.KNOWLEDGE_BASE_DIR and settings.DOCUMENTS_DIR.
    """
    search_dirs = []
    if hasattr(settings, "KNOWLEDGE_BASE_DIR") and settings.KNOWLEDGE_BASE_DIR.exists():
        search_dirs.append(settings.KNOWLEDGE_BASE_DIR)
    if hasattr(settings, "DOCUMENTS_DIR") and settings.DOCUMENTS_DIR.exists():
        if settings.DOCUMENTS_DIR not in search_dirs:
            search_dirs.append(settings.DOCUMENTS_DIR)

    discovered_files: Dict[str, Path] = {}

    for s_dir in search_dirs:
        logger.info(f"Scanning directory recursively: {s_dir}")
        for path in s_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                # Key by filename to prevent duplicates across symlinks or overlapping paths
                if path.name not in discovered_files:
                    discovered_files[path.name] = path

    file_list = sorted(list(discovered_files.values()), key=lambda p: p.name.lower())
    logger.info(f"Total supported documents discovered: {len(file_list)}")
    return file_list


def run_ingestion(db: Session = None) -> List[Dict[str, Any]]:
    """
    Executes the enterprise idempotent ingestion pipeline:
    1. Recursively discovers all PDF, TXT, and Markdown files across the knowledge base.
    2. Computes SHA-256 hashes for strict idempotency (skips unchanged documents).
    3. Safely purges and re-indexes modified documents.
    4. Applies structure-aware, hierarchical chunking for procedures, tables, and sections.
    5. Generates 384-dimensional dense embeddings in high-throughput batches.
    6. Stores chunk records and invalidates retrieval memory caches.
    """
    should_close_db = False
    if db is None:
        init_db()
        db = SessionLocal()
        should_close_db = True

    results = []
    doc_files = discover_knowledge_base_files()

    if not doc_files:
        logger.warning("No documents found in knowledge base directories.")
        if should_close_db:
            db.close()
        return results

    BATCH_EMBED_SIZE = 64

    for doc_path in doc_files:
        filename = doc_path.name
        file_hash = document_service.compute_file_hash(doc_path)

        # Idempotency check: check if document already exists with same hash and valid chunks
        existing_doc = db.query(Document).filter(Document.filename == filename).first()
        if existing_doc and existing_doc.file_hash == file_hash:
            chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == existing_doc.id).count()
            if chunk_count > 0:
                logger.info(f"Skipping '{filename}': already ingested with identical checksum ({chunk_count} chunks).")
                results.append({
                    "filename": filename,
                    "status": "skipped",
                    "reason": "already_up_to_date",
                    "chunks": chunk_count
                })
                continue

        logger.info(f"Processing document: '{filename}' ({doc_path.stat().st_size / (1024 * 1024):.2f} MB) ...")
        pages = document_service.extract_document_pages(doc_path)
        page_count = len(pages)

        # If document already exists with different hash, purge old chunks safely
        if existing_doc:
            logger.info(f"Updating existing document '{filename}' (reindexing new contents).")
            db.query(DocumentChunk).filter(DocumentChunk.document_id == existing_doc.id).delete()
            existing_doc.file_hash = file_hash
            existing_doc.page_count = page_count
            doc_record = existing_doc
        else:
            doc_info = document_service.get_document_info(filename)
            doc_record = Document(
                filename=filename,
                title=doc_info["title"],
                file_hash=file_hash,
                version="1.0",
                page_count=page_count
            )
            db.add(doc_record)
            db.commit()
            db.refresh(doc_record)

        # Generate structure-aware hierarchical chunks
        all_chunk_dicts = []
        for page_data in pages:
            page_num = page_data["page_number"]
            page_text = page_data["text"]
            active_section = page_data.get("active_section", "Overview")
            active_subsection = page_data.get("active_subsection", "")

            chunks = document_service.chunk_page_text(
                text=page_text,
                page_number=page_num,
                document_name=filename,
                active_section=active_section,
                active_subsection=active_subsection
            )
            all_chunk_dicts.extend(chunks)

        total_chunks = len(all_chunk_dicts)
        logger.info(f"Generated {total_chunks} structure-aware chunks for '{filename}'. Generating embeddings in batches...")

        # Process embeddings and database insertion in streaming batches
        inserted_chunks = 0
        for i in range(0, total_chunks, BATCH_EMBED_SIZE):
            batch = all_chunk_dicts[i : i + BATCH_EMBED_SIZE]
            texts_to_embed = [c["chunk_text"] for c in batch]
            embeddings = embedding_service.embed_batch(texts_to_embed)

            for j, chunk_data in enumerate(batch):
                meta = dict(chunk_data["metadata"])
                meta["document_id"] = doc_record.id

                chunk_record = DocumentChunk(
                    document_id=doc_record.id,
                    document_name=filename,
                    chunk_index=i + j,
                    page_number=chunk_data["page_number"],
                    section=chunk_data["section"],
                    chunk_text=chunk_data["chunk_text"],
                    metadata_json=json.dumps(meta),
                    embedding=embeddings[j]
                )
                db.add(chunk_record)
                inserted_chunks += 1

            db.commit()
            if total_chunks > 100:
                logger.info(f"Progress '{filename}': {inserted_chunks}/{total_chunks} chunks embedded and saved.")

        logger.info(f"Successfully ingested '{filename}': {page_count} pages, {inserted_chunks} chunks.")
        results.append({
            "filename": filename,
            "status": "ingested",
            "page_count": page_count,
            "chunks": inserted_chunks
        })

    # Invalidate retrieval in-memory cache to make all newly indexed vectors immediately searchable
    try:
        retrieval_service.invalidate_cache()
        logger.info("Retrieval service cache invalidated. New vectors are live.")
    except Exception as e:
        logger.warning(f"Could not invalidate retrieval cache: {e}")

    if should_close_db:
        db.close()

    return results


if __name__ == "__main__":
    logger.info("Starting Enterprise RAG Ingestion Pipeline...")
    res = run_ingestion()
    logger.info(f"Ingestion finished. Summary: {res}")
