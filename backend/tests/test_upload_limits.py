import asyncio
import io

import pytest

from backend.app.config import settings
from backend.app.security.uploads import UploadLimitError, spool_limited_upload
from backend.app.services.document_extractor import PDFPageLimitError, extract_from_pdf
from backend.app.services.document_processing_service import allowed_upload_extensions, validate_upload_signature


class FakeUpload:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.read_count = 0

    async def read(self, _size):
        self.read_count += 1
        return next(self.chunks, b"")


def test_upload_spools_chunks_and_tracks_size_and_signature_prefix():
    upload = FakeUpload([b"hello", b" world"])
    spool, size, prefix = asyncio.run(spool_limited_upload(
        upload, max_file_bytes=32, remaining_total_bytes=32, chunk_size=8
    ))
    try:
        assert size == 11
        assert prefix == b"hello world"
        assert spool.read() == b"hello world"
        assert upload.read_count == 3
    finally:
        spool.close()


def test_upload_spool_enforces_per_file_and_batch_caps():
    with pytest.raises(UploadLimitError, match="per-file"):
        asyncio.run(spool_limited_upload(FakeUpload([b"1234"]), max_file_bytes=3, remaining_total_bytes=100))
    with pytest.raises(UploadLimitError, match="total size"):
        asyncio.run(spool_limited_upload(FakeUpload([b"1234"]), max_file_bytes=10, remaining_total_bytes=3))


def test_signature_validation_rejects_extension_mismatch():
    validate_upload_signature("readme.txt", b"SAP BRIM guide")
    validate_upload_signature("scan.pdf", b"%PDF-1.7\n")
    with pytest.raises(ValueError, match="does not match"):
        validate_upload_signature("scan.pdf", b"not a PDF")
    with pytest.raises(ValueError, match="does not match"):
        validate_upload_signature("screen.png", b"plain text")


def test_risky_document_extensions_are_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_EXTENDED_UPLOAD_TYPES", False)
    assert ".json" not in allowed_upload_extensions()
    assert ".sql" not in allowed_upload_extensions()
    monkeypatch.setattr(settings, "ALLOW_EXTENDED_UPLOAD_TYPES", True)
    assert {".json", ".sql", ".xml", ".yaml", ".yml"}.issubset(allowed_upload_extensions())


def test_pdf_extraction_rejects_page_count_over_configured_cap(monkeypatch):
    import fitz

    class FakeDocument:
        def __len__(self):
            return 3

        def close(self):
            self.closed = True

    monkeypatch.setattr(settings, "MAX_PDF_PAGES", 2)
    monkeypatch.setattr(fitz, "open", lambda **_kwargs: FakeDocument())
    with pytest.raises(PDFPageLimitError, match="2-page limit"):
        extract_from_pdf("many.pdf", b"%PDF-1.7")
