import io
import time
import pytest
import numpy as np
from PIL import Image
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models.document import Document
from backend.app.models.chunk import DocumentChunk
from backend.app.services.document_processing_service import document_processing_service
from backend.app.services.retrieval_service import retrieval_service


def _create_sample_png():
    output = io.BytesIO()
    Image.new("RGB", (100, 50), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def client():
    # These tests exercise document processing, not authorization (covered by test_admin_portal_security);
    # document management requires an administrator, so act as one.
    from backend.app.api.documents import authenticate_document_operator
    app.dependency_overrides[authenticate_document_operator] = lambda: SimpleNamespace(id="test-admin", is_admin=True)
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    yield db
    db.close()


def test_document_listing_and_counts(client):
    """Test GET /api/documents returns correct summary and structure."""
    response = client.get("/api/documents")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "documents" in data
    assert "counts" in data
    assert "all" in data["counts"]
    assert "pending" in data["counts"]
    assert "completed" in data["counts"]
    assert "failed" in data["counts"]
    assert isinstance(data["documents"], list)


def test_admin_can_classify_source_tier_and_invalidate_retrieval_cache(client):
    from backend.app.api.documents import SourceTierUpdate, set_document_source_tier

    document = SimpleNamespace(id="test-doc", source_tier="self_authored")
    query = SimpleNamespace(filter=lambda *_args, **_kwargs: SimpleNamespace(first=lambda: document))
    session = SimpleNamespace(query=lambda *_args: query, commit=lambda: None)
    request = SimpleNamespace()

    with patch("backend.app.api.documents.audit_log.record") as record, \
            patch.object(retrieval_service, "invalidate_cache") as invalidate:
        result = set_document_source_tier(
            "test-doc", SourceTierUpdate(source_tier="official_sap"), request, session, "test-admin"
        )

    assert result == {"id": "test-doc", "source_tier": "official_sap"}
    record.assert_called_once()
    invalidate.assert_called_once()


def test_upload_multiple_documents_and_safe_deduplication(client, db_session):
    """Test uploading multiple new files and ensuring safe registration without overwriting."""
    test_txt_bytes = b"SAP BRIM CI CIT BIT integration and billing process documentation."
    test_md_bytes = b"# SAP BRIM Billing\n\nDetailed configuration of billing schedules."

    # 1. Upload two new documents
    resp = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("integration_test_doc_1.txt", test_txt_bytes, "text/plain")),
            ("files", ("integration_test_doc_2.md", test_md_bytes, "text/markdown")),
        ],
    )
    assert resp.status_code == 201, resp.text
    result = resp.json()
    assert result["status"] == "success"
    assert result["registered_count"] == 2
    uploaded_docs = result["documents"]
    doc1_id = uploaded_docs[0]["id"]
    doc2_id = uploaded_docs[1]["id"]
    assert db_session.query(Document).filter(Document.id == doc1_id).one().source_tier == "self_authored"

    try:
        # Verify both appear with status "pending"
        pending_resp = client.get("/api/documents?status=pending")
        assert pending_resp.status_code == 200
        pending_ids = [d["id"] for d in pending_resp.json()["documents"]]
        assert doc1_id in pending_ids
        assert doc2_id in pending_ids

        # 2. Test duplicate upload with different content to verify safe non-overwriting behavior
        different_content = b"Updated different content for integration test doc 1."
        dup_resp = client.post(
            "/api/documents/upload",
            files=[
                ("files", ("integration_test_doc_1.txt", different_content, "text/plain")),
            ],
        )
        assert dup_resp.status_code == 201
        dup_result = dup_resp.json()
        assert dup_result["registered_count"] == 1
        dup_doc_id = dup_result["documents"][0]["id"]
        # Ensure it got a unique registered document ID and didn't corrupt the previous doc
        assert dup_doc_id != doc1_id

        # Clean up dup doc
        client.delete(f"/api/documents/{dup_doc_id}")

    finally:
        # Clean up test documents
        client.delete(f"/api/documents/{doc1_id}")
        client.delete(f"/api/documents/{doc2_id}")


def test_one_click_document_processing_pipeline(client, db_session):
    """
    Test full end-to-end processing pipeline:
    Validate -> Extract -> OCR / Text -> Chunk -> Embed -> Store Vectors -> Verify Storage -> Completed.
    """
    content = (
        "Procedure: How to activate a Subscription Provider Contract in SAP BRIM SOM.\n"
        "Prerequisites: Ensure Business Partner and Contract Account (VKONT) exist.\n"
        "Step 1: Execute transaction /nCRM_UI or open Fiori Launchpad.\n"
        "Step 2: Navigate to Subscription Orders and create a new contract order.\n"
        "Step 3: Submit order to trigger Order Distribution Infrastructure (ODI).\n"
        "Result: Provider Contract status changes to ACTIVE and synchronizes to Convergent Charging."
    )
    test_filename = "contract_activation_test_procedure.txt"

    # Upload test document
    upload_resp = client.post(
        "/api/documents/upload",
        files=[("files", (test_filename, content.encode("utf-8"), "text/plain"))],
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["documents"][0]["id"]

    try:
        # Execute processing synchronously in test
        document_processing_service._execute_pipeline(db_session, document_ids=[doc_id], force=True)

        # Inspect document from API
        doc_details_resp = client.get(f"/api/documents/{doc_id}")
        assert doc_details_resp.status_code == 200
        doc_details = doc_details_resp.json()

        assert doc_details["status"] == "completed"
        assert doc_details["vector_indexed"] is True
        assert doc_details["chunk_count"] > 0
        assert doc_details["error_message"] is None
        assert len(doc_details["sample_chunks"]) > 0
        assert doc_details["sample_chunks"][0]["has_embedding"] is True

        # Verify live processing status
        status_resp = client.get("/api/documents/processing-status")
        assert status_resp.status_code == 200
        progress_data = status_resp.json()
        assert progress_data["summary"] is not None
        assert progress_data["summary"]["vector_database_verification"] == "Successful"

        # Verify vectors in DB
        chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
        assert len(chunks) == doc_details["chunk_count"]
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 384
            assert chunk.document_id == doc_id

    finally:
        # Clean up
        client.delete(f"/api/documents/{doc_id}")


def test_image_document_ocr_processing(client, db_session):
    """Test uploading an image file and running OCR extraction and chunking."""
    png_filename = "sap_architecture_diagram_test.png"
    fake_ocr_output = SimpleNamespace(
        boxes=np.asarray([[[5, 5], [100, 5], [100, 20], [5, 20]]], dtype=float),
        txts=("Convergent Charging Core Tool Rating Tree and Subscriber Account",),
    )

    upload_resp = client.post(
        "/api/documents/upload",
        files=[("files", (png_filename, _create_sample_png(), "image/png"))],
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["documents"][0]["id"]

    try:
        with patch("backend.app.services.document_extractor._get_ocr_engine", return_value=lambda _img: fake_ocr_output):
            document_processing_service._execute_pipeline(db_session, document_ids=[doc_id], force=True)

        # Verify processed status
        doc_resp = client.get(f"/api/documents/{doc_id}")
        assert doc_resp.status_code == 200
        doc = doc_resp.json()
        assert doc["status"] == "completed"
        assert doc["vector_indexed"] is True
        assert "Rating Tree" in doc["sample_chunks"][0]["text_preview"]

    finally:
        client.delete(f"/api/documents/{doc_id}")


def test_document_deletion_and_vector_database_synchronization(client, db_session):
    """
    Test deleting a document:
    - Removes document record
    - Purges all associated vectors from document_chunks table
    - Deletes file from disk
    - Invalidates retrieval service cache
    """
    content = "Unique test term XY789QZ for deletion verification."
    filename = "deletion_test_doc.txt"

    # Upload and process
    upload_resp = client.post(
        "/api/documents/upload",
        files=[("files", (filename, content.encode("utf-8"), "text/plain"))],
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["documents"][0]["id"]

    # Process document
    document_processing_service._execute_pipeline(db_session, document_ids=[doc_id], force=True)

    # Verify vectors exist before deletion
    pre_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()
    assert pre_chunks > 0

    # Delete document
    del_resp = client.delete(f"/api/documents/{doc_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["success"] is True
    assert del_data["deleted_document_id"] == doc_id
    assert del_data["deleted_chunks"] == pre_chunks

    # Verify 0 chunks remain in vector DB
    post_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()
    assert post_chunks == 0

    # Verify document no longer exists in DB
    post_doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert post_doc is None

    # Verify retrieval cache cannot retrieve the deleted term
    results = retrieval_service.hybrid_search(db_session, "XY789QZ", top_k=5)
    matching_deleted_doc = [r for r in results if r.get("document_id") == doc_id]
    assert len(matching_deleted_doc) == 0


def test_error_handling_and_retry_flow(client, db_session):
    """Test handling corrupted/empty document, transitioning to Failed, and retrying."""
    from backend.app.config import settings
    filename = "corrupted_empty_file.txt"

    # Upload document with empty content (will fail extraction)
    upload_resp = client.post(
        "/api/documents/upload",
        files=[("files", (filename, b"   ", "text/plain"))],
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["documents"][0]["id"]

    try:
        # Run processing
        document_processing_service._execute_pipeline(db_session, document_ids=[doc_id], force=True)

        # Check status is Failed with descriptive error
        doc_resp = client.get(f"/api/documents/{doc_id}")
        assert doc_resp.status_code == 200
        doc_data = doc_resp.json()
        assert doc_data["status"] == "failed"
        assert doc_data["error_message"] is not None
        assert "readable text" in doc_data["error_message"].lower() or "empty" in doc_data["error_message"].lower()

        # Retry with fixed content
        file_path = settings.DOCUMENTS_DIR / filename
        with open(file_path, "wb") as f:
            f.write(b"Fixed valid content: SAP BRIM Billing document with complete transaction items.")

        # Execute retry pipeline directly
        document_processing_service._execute_pipeline(db_session, document_ids=[doc_id], force=True)

        # Check document successfully transitioned to completed
        doc_after_retry = client.get(f"/api/documents/{doc_id}").json()
        assert doc_after_retry["status"] == "completed"
        assert doc_after_retry["vector_indexed"] is True
        assert doc_after_retry["chunk_count"] > 0
        assert doc_after_retry["error_message"] is None

    finally:
        client.delete(f"/api/documents/{doc_id}")
