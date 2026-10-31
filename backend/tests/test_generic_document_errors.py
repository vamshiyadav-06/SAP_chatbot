import logging
import io
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api import documents as documents_module
from backend.app.api.documents import authenticate_document_operator
from backend.app.main import app
from backend.app.services import document_processing_service as processing_module


def test_document_delete_returns_generic_error_and_logs_details(monkeypatch, caplog):
    secret_detail = "database path C:/private/storage/driver failure"

    def fail_delete(**_kwargs):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(processing_module.document_processing_service, "delete_document", fail_delete)
    app.dependency_overrides[authenticate_document_operator] = lambda: SimpleNamespace(id="test-admin", is_admin=True)
    try:
        with TestClient(app) as client, caplog.at_level(logging.ERROR):
            response = client.delete("/api/documents/test-id")
    finally:
        app.dependency_overrides.pop(authenticate_document_operator, None)

    assert response.status_code == 500
    assert response.json()["detail"] == "DOCUMENT_DELETE_FAILED"
    assert secret_detail not in response.text
    assert secret_detail in caplog.text


def test_processing_worker_broadcasts_generic_error(monkeypatch, caplog):
    secret_detail = "private parser path C:/private/file.pdf"
    events = []

    class FakeSession:
        def close(self):
            pass

    service = processing_module.document_processing_service
    monkeypatch.setattr(processing_module, "SessionLocal", FakeSession)
    monkeypatch.setattr(service, "_execute_pipeline", lambda *_args: (_ for _ in ()).throw(RuntimeError(secret_detail)))
    monkeypatch.setattr(service, "_broadcast", events.append)

    with caplog.at_level(logging.ERROR):
        service._process_worker(None, False)

    assert events[0]["current_stage"] == "DOCUMENT_PROCESSING_FAILED"
    assert secret_detail not in str(events)
    assert secret_detail in caplog.text


def test_document_upload_returns_generic_code_and_logs_details(monkeypatch, caplog):
    secret_detail = "private storage path C:/private/upload.pdf"

    async def fake_spool(*_args, **_kwargs):
        content = b"%PDF-1.7"
        return io.BytesIO(content), len(content), content[:8]

    def fail_register(**_kwargs):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(documents_module, "spool_limited_upload", fake_spool)
    monkeypatch.setattr(documents_module.document_processing_service, "register_uploaded_file", fail_register)
    app.dependency_overrides[authenticate_document_operator] = lambda: SimpleNamespace(id="test-admin", is_admin=True)
    try:
        with TestClient(app) as client, caplog.at_level(logging.ERROR):
            response = client.post("/api/documents/upload", files={"files": ("report.pdf", b"%PDF-1.7", "application/pdf")})
    finally:
        app.dependency_overrides.pop(authenticate_document_operator, None)

    assert response.status_code == 201
    assert response.json()["errors"] == [{"filename": "report.pdf", "error": "UPLOAD_FAILED"}]
    assert secret_detail not in response.text
    assert secret_detail in caplog.text
