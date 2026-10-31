import io
import re
import logging
from functools import lru_cache
from typing import Dict, Any, List, Optional
from pathlib import Path
from backend.app.config import settings
from backend.app.security.log_safety import privacy_fingerprint

logger = logging.getLogger(__name__)

MAX_CHARACTERS_PER_DOCUMENT = 150000
MAX_IMAGE_PIXELS = 25_000_000


class PDFPageLimitError(ValueError):
    pass


def clean_extracted_text(text: str) -> str:
    """Cleans raw text by removing non-printable glyphs and normalizing whitespace."""
    if not text:
        return ""
    # Filter private-use unicode glyphs and replacement chars
    text = re.sub(r"[\ue000-\uf8ff\ufffd]", " ", text)
    # Normalize line breaks and tabs
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_from_pdf(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """Extracts text, pages, and metadata from PDF bytes using PyMuPDF with PyPDF fallback."""
    pages_list: List[Dict[str, Any]] = []
    full_text_chunks: List[str] = []
    page_count = 0

    # 1. Primary extractor: PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(doc)
        if page_count > settings.MAX_PDF_PAGES:
            doc.close()
            raise PDFPageLimitError(f"PDF exceeds the configured {settings.MAX_PDF_PAGES}-page limit.")

        for page_idx in range(page_count):
            page = doc[page_idx]
            page_num = page_idx + 1
            raw_page_text = page.get_text("text") or ""
            cleaned = clean_extracted_text(raw_page_text)

            pages_list.append({
                "page": page_num,
                "text": cleaned,
                "char_count": len(cleaned)
            })
            if cleaned:
                full_text_chunks.append(f"--- Page {page_num} ---\n{cleaned}")
        doc.close()
    except PDFPageLimitError:
        raise
    except Exception as e_fitz:
        logger.warning("PyMuPDF extraction failed for document_ref=%s (%s); falling back to pypdf.", privacy_fingerprint(filename), type(e_fitz).__name__)
        # 2. Fallback extractor: pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            page_count = len(reader.pages)
            if page_count > settings.MAX_PDF_PAGES:
                raise PDFPageLimitError(f"PDF exceeds the configured {settings.MAX_PDF_PAGES}-page limit.")
            for page_idx, page in enumerate(reader.pages):
                page_num = page_idx + 1
                raw_text = page.extract_text() or ""
                cleaned = clean_extracted_text(raw_text)
                pages_list.append({
                    "page": page_num,
                    "text": cleaned,
                    "char_count": len(cleaned)
                })
                if cleaned:
                    full_text_chunks.append(f"--- Page {page_num} ---\n{cleaned}")
        except PDFPageLimitError:
            raise
        except Exception as e_pypdf:
            logger.error("pypdf extraction also failed for document_ref=%s (%s)", privacy_fingerprint(filename), type(e_pypdf).__name__)
            raise ValueError(f"Failed to extract text from PDF '{filename}': {e_pypdf}")

    full_text = "\n\n".join(full_text_chunks).strip()
    if len(full_text) > MAX_CHARACTERS_PER_DOCUMENT:
        marker = "\n\n[Document content truncated to fit token limits]"
        full_text = full_text[:MAX_CHARACTERS_PER_DOCUMENT - len(marker)] + marker

    preview = full_text[:300].strip() + ("..." if len(full_text) > 300 else "")

    return {
        "filename": filename,
        "file_type": "pdf",
        "size_bytes": len(file_bytes),
        "page_count": page_count,
        "char_count": len(full_text),
        "preview": preview,
        "text": full_text,
        "pages": pages_list,
    }


def extract_from_docx(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """Extracts text from Word DOCX bytes including paragraphs, headings, and tables."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs: List[str] = []

        for p in doc.paragraphs:
            text = clean_extracted_text(p.text)
            if text:
                if p.style and p.style.name.startswith("Heading"):
                    paragraphs.append(f"### {text}")
                else:
                    paragraphs.append(text)

        # Extract table content
        for t_idx, table in enumerate(doc.tables, 1):
            table_rows: List[str] = []
            for row in table.rows:
                row_cells = [clean_extracted_text(cell.text) for cell in row.cells]
                table_rows.append(" | ".join(row_cells))
            if table_rows:
                paragraphs.append(f"\n[Table {t_idx}]\n" + "\n".join(table_rows))

        full_text = "\n\n".join(paragraphs).strip()
        if len(full_text) > MAX_CHARACTERS_PER_DOCUMENT:
            marker = "\n\n[Document content truncated to fit token limits]"
            full_text = full_text[:MAX_CHARACTERS_PER_DOCUMENT - len(marker)] + marker

        preview = full_text[:300].strip() + ("..." if len(full_text) > 300 else "")

        return {
            "filename": filename,
            "file_type": "docx",
            "size_bytes": len(file_bytes),
            "page_count": max(1, len(paragraphs) // 15),
            "char_count": len(full_text),
            "preview": preview,
            "text": full_text,
            "pages": [],
        }
    except Exception as e:
        logger.error("DOCX extraction failed for document_ref=%s (%s)", privacy_fingerprint(filename), type(e).__name__)
        raise ValueError(f"Failed to extract text from DOCX document '{filename}': {e}")


def extract_from_plaintext(filename: str, file_bytes: bytes, file_type: str) -> Dict[str, Any]:
    """Extracts text from plain text, markdown, CSV, JSON, or log files."""
    text = ""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    cleaned = clean_extracted_text(text)
    if len(cleaned) > MAX_CHARACTERS_PER_DOCUMENT:
        marker = "\n\n[Document content truncated to fit token limits]"
        cleaned = cleaned[:MAX_CHARACTERS_PER_DOCUMENT - len(marker)] + marker

    line_count = len(cleaned.splitlines())
    estimated_pages = max(1, line_count // 45)
    preview = cleaned[:300].strip() + ("..." if len(cleaned) > 300 else "")

    return {
        "filename": filename,
        "file_type": file_type,
        "size_bytes": len(file_bytes),
        "page_count": estimated_pages,
        "char_count": len(cleaned),
        "preview": preview,
        "text": cleaned,
        "pages": [],
    }


@lru_cache(maxsize=1)
def _get_ocr_engine():
    """Initialize the local OCR engine on demand and reuse it across uploads."""
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise ValueError(
            "PNG OCR is unavailable. Install the backend OCR dependencies and restart the API."
        ) from exc
    return RapidOCR()


def extract_from_png(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """Extract text and a simple reading-order description from an uploaded PNG."""
    if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The uploaded file is not a valid PNG image.")
    try:
        from PIL import Image, ImageOps
        import numpy as np

        with Image.open(io.BytesIO(file_bytes)) as source_image:
            if source_image.format != "PNG":
                raise ValueError("The uploaded file is not a valid PNG image.")
            width, height = source_image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("PNG dimensions exceed the supported image size.")
            image = ImageOps.exif_transpose(source_image).convert("RGB")
            ocr_result = _get_ocr_engine()(np.asarray(image))

        text_blocks = []
        boxes = getattr(ocr_result, "boxes", None) if ocr_result else None
        recognized = getattr(ocr_result, "txts", None) if ocr_result else None
        for box, detected_text in zip(
            boxes if boxes is not None else [],
            recognized if recognized is not None else [],
        ):
            detected_text = clean_extracted_text(str(detected_text))
            if not detected_text:
                continue
            try:
                top = min(float(point[1]) for point in box)
                left = min(float(point[0]) for point in box)
            except (TypeError, ValueError, IndexError):
                top, left = 0.0, 0.0
            text_blocks.append((top, left, detected_text))

        # OCR boxes retain useful ordering for screenshots, forms, and diagrams.
        text_blocks.sort(key=lambda block: (round(block[0] / 20), block[1]))
        recognized_lines = [block[2] for block in text_blocks]
        if not recognized_lines:
            raise ValueError("No readable text was detected in this PNG image.")

        extracted_text = (
            f"Image: {Path(filename).name} ({width} x {height} pixels)\n"
            "OCR text in approximate top-to-bottom, left-to-right reading order:\n"
            + "\n".join(recognized_lines)
        )
        extracted_text = clean_extracted_text(extracted_text)[:MAX_CHARACTERS_PER_DOCUMENT]
        return {
            "filename": Path(filename).name,
            "file_type": "png",
            "size_bytes": len(file_bytes),
            "page_count": 1,
            "char_count": len(extracted_text),
            "preview": extracted_text[:300] + ("..." if len(extracted_text) > 300 else ""),
            "text": extracted_text,
            "pages": [{"page": 1, "text": extracted_text, "char_count": len(extracted_text)}],
        }
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("PNG OCR failed for document_ref=%s (%s)", privacy_fingerprint(Path(filename).name), type(exc).__name__)
        raise ValueError(f"Could not read text from PNG image '{Path(filename).name}'.") from exc


def extract_from_image(filename: str, file_bytes: bytes, file_type: str = "image") -> Dict[str, Any]:
    """Extract text from JPG, WEBP, BMP, TIFF or general image bytes using OCR."""
    try:
        from PIL import Image, ImageOps
        import numpy as np

        with Image.open(io.BytesIO(file_bytes)) as source_image:
            width, height = source_image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError(f"{file_type.upper()} dimensions exceed the supported image size.")
            image = ImageOps.exif_transpose(source_image).convert("RGB")
            ocr_result = _get_ocr_engine()(np.asarray(image))

        text_blocks = []
        boxes = getattr(ocr_result, "boxes", None) if ocr_result else None
        recognized = getattr(ocr_result, "txts", None) if ocr_result else None
        for box, detected_text in zip(
            boxes if boxes is not None else [],
            recognized if recognized is not None else [],
        ):
            detected_text = clean_extracted_text(str(detected_text))
            if not detected_text:
                continue
            try:
                top = min(float(point[1]) for point in box)
                left = min(float(point[0]) for point in box)
            except (TypeError, ValueError, IndexError):
                top, left = 0.0, 0.0
            text_blocks.append((top, left, detected_text))

        text_blocks.sort(key=lambda block: (round(block[0] / 20), block[1]))
        recognized_lines = [block[2] for block in text_blocks]
        if not recognized_lines:
            raise ValueError(f"No readable text was detected in this {file_type.upper()} image.")

        extracted_text = (
            f"Image: {Path(filename).name} ({width} x {height} pixels)\n"
            "OCR text in approximate reading order:\n"
            + "\n".join(recognized_lines)
        )
        extracted_text = clean_extracted_text(extracted_text)[:MAX_CHARACTERS_PER_DOCUMENT]
        return {
            "filename": Path(filename).name,
            "file_type": file_type,
            "size_bytes": len(file_bytes),
            "page_count": 1,
            "char_count": len(extracted_text),
            "preview": extracted_text[:300] + ("..." if len(extracted_text) > 300 else ""),
            "text": extracted_text,
            "pages": [{"page": 1, "text": extracted_text, "char_count": len(extracted_text)}],
        }
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("Image OCR failed for document_ref=%s (%s)", privacy_fingerprint(Path(filename).name), type(exc).__name__)
        raise ValueError(f"Could not read text from image '{Path(filename).name}': {exc}") from exc


def extract_document(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Main extraction dispatcher.
    Accepts PDF, DOCX, PNG, JPG, JPEG, WEBP, BMP, TXT, MD, CSV, JSON, and LOG files.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext:
        ext = "txt"

    if ext == "pdf":
        return extract_from_pdf(filename, file_bytes)
    elif ext == "png":
        return extract_from_png(filename, file_bytes)
    elif ext in ("jpg", "jpeg", "webp", "bmp", "tiff"):
        return extract_from_image(filename, file_bytes, ext)
    elif ext == "docx":
        return extract_from_docx(filename, file_bytes)
    elif ext in ("txt", "md", "csv", "json", "log", "tsv", "xml", "sql", "yaml", "yml"):
        return extract_from_plaintext(filename, file_bytes, ext)
    else:
        raise ValueError(
            f"Unsupported file format '.{ext}'. Supported formats are: PDF, DOCX, PNG, JPG, WEBP, TXT, MD, CSV, JSON, LOG, TSV, XML, SQL, and YAML."
        )
