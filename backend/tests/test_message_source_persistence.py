from backend.app.api.messages import source_rows
from backend.app.models.citation import Citation
from backend.app.models.web_image import WebImage
from backend.app.models.web_source import WebSource


def test_source_rows_fit_postgres_varchar_limits():
    """Over-long web metadata must not abort saving the answer (PostgreSQL enforces VARCHAR)."""
    long_text = "Transferring billable items " * 100  # 2800 chars
    rows = source_rows(
        "msg-1",
        citations=[{"document": "x" * 400, "page": 1, "section": long_text, "score": 0.9, "snippet": "s"}],
        web_sources=[
            {"url": "https://help.sap.com/a", "title": long_text, "domain": "help.sap.com", "snippet": "s"},
            {"url": "https://help.sap.com/" + "p" * 1200, "title": "too long url", "domain": "help.sap.com"},
        ],
        images=[
            {"url": "https://help.sap.com/img.png", "alt_text": long_text, "source_title": long_text,
             "source_url": "https://help.sap.com/" + "q" * 2100, "description": long_text},
            {"url": "https://help.sap.com/" + "r" * 2100},
        ],
    )

    citations = [r for r in rows if isinstance(r, Citation)]
    sources = [r for r in rows if isinstance(r, WebSource)]
    images = [r for r in rows if isinstance(r, WebImage)]

    assert len(citations) == 1 and len(citations[0].document_name) <= 255 and len(citations[0].section) <= 255
    assert len(citations[0].document_id) <= 300
    assert len(sources) == 1 and len(sources[0].title) <= 500
    assert len(images) == 1
    assert len(images[0].alt_text) <= 1000 and len(images[0].source_title) <= 500
    assert images[0].source_url is None  # clipped URLs would be broken links
    assert images[0].description == long_text  # TEXT column, kept whole
