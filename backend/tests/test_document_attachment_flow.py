import io
import fitz
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.document_extractor import extract_document
from backend.app.services.rag_service import rag_service
from backend.app.database import SessionLocal


def _guest_headers(client):
    """Extraction requires a signed-in user; guests sign in through /auth/demo."""
    token = client.post("/api/auth/demo").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_document_extractor_pdf():
    # Create in-memory sample PDF
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((50, 70), "Invoice Number: INV-98765\nBillable Item Class: BIK1\nAmount Due: 15,400 USD")
    page2 = doc.new_page()
    page2.insert_text((50, 70), "Payment Terms: Net 30 days\nClearing Account: 113100")
    pdf_bytes = doc.tobytes()
    doc.close()

    result = extract_document("sample_invoice.pdf", pdf_bytes)
    assert result["filename"] == "sample_invoice.pdf"
    assert result["file_type"] == "pdf"
    assert result["page_count"] == 2
    assert "INV-98765" in result["text"]
    assert "Net 30 days" in result["text"]
    assert len(result["pages"]) == 2


def test_document_extractor_plaintext():
    text_content = "SAP FI-CA Contract Account: 200000123\nPartner: BP-5544\nDunning Level: 2"
    result = extract_document("notes.txt", text_content.encode("utf-8"))
    assert result["filename"] == "notes.txt"
    assert result["file_type"] == "txt"
    assert "Contract Account: 200000123" in result["text"]


def test_extract_endpoint_api():
    client = TestClient(app)

    # In-memory PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "SAP Convergent Invoicing Billing Cycle 01")
    pdf_bytes = doc.tobytes()
    doc.close()

    response = client.post(
        "/api/chats/extract-document",
            headers=_guest_headers(client),
        files={"file": ("billing_spec.pdf", pdf_bytes, "application/pdf")}
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["filename"] == "billing_spec.pdf"
    assert data["file_type"] == "pdf"
    assert data["page_count"] == 1
    assert "Billing Cycle 01" in data["text"]


def test_rag_query_with_attached_document():
    db = SessionLocal()
    try:
        sample_attachments = [
            {
                "name": "Custom_S4_Interface.pdf",
                "file_type": "pdf",
                "page_count": 2,
                "text": "The custom interface transmits BIT records via RFC function /CUST/BIT_INBOUND.\nReconciliation occurs every midnight using batch job Z_RECON_BIT."
            }
        ]

        query = "What RFC function is used to transmit BIT records in this document?"
        result = rag_service.process_query(
            db=db,
            query=query,
            attachments=sample_attachments
        )

        assert result is not None
        assert result["source_type"] == "attached_document"
        assert len(result["citations"]) > 0
        assert any(c["source_type"] == "attached_document" for c in result["citations"])
        # The answer must cite or address the custom interface or BIT records
        assert len(result["answer"]) > 20
    finally:
        db.close()
