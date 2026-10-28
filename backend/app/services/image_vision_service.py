"""
Vision-LLM reading of images attached to a chat (screenshots, error dialogs, diagrams).

A vision model describes the image, transcribes its visible text and pins down any
question or error it shows. Local OCR runs alongside as an exact-character cross-check
for codes and message numbers, and is the only reader when every vision model fails.
The analysis is factual only; the regular grounded answer pipeline produces the fix.
"""
import base64
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings
from backend.app.services.document_extractor import (
    MAX_CHARACTERS_PER_DOCUMENT,
    MAX_IMAGE_PIXELS,
    clean_extracted_text,
    extract_document,
)

logger = logging.getLogger(__name__)

CHAT_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "webp", "bmp")
# Longest side sent to the vision model; larger screenshots are downscaled.
MAX_VISION_SIDE = 2000
# Provider limit for inline base64 images is ~4 MB; stay safely below it.
MAX_VISION_PAYLOAD_BYTES = 3_500_000

VISION_SYSTEM_PROMPT = (
    "You read images that users attach to an SAP support assistant. Report only what "
    "is visible in the image. Do not guess beyond it and do not propose fixes."
)

VISION_USER_PROMPT = """Analyse the attached image and respond in exactly this format:

## Image Summary
2-4 sentences: what kind of image it is (for example a screenshot of a specific SAP transaction or application screen, an error dialog, a log, a diagram, a photo of a document) and what it shows.

## Visible Text
Transcribe all readable text verbatim, line by line. Keep error codes, message numbers, message classes, transaction codes, table names, field names and values exactly as shown.

## Detected Question or Problem
The question, error, warning or problem the image shows, stated precisely with its exact codes and message text. Write "None" if the image shows no question or problem.

DETECTED_QUESTION: <one line restating that question or problem as a question to answer, for example "How do I resolve SAP message <exact message> in transaction <code>?", or NONE>"""

_DETECTED_RE = re.compile(r"^\s*\**DETECTED_QUESTION\**\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def is_chat_image(filename: str) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in CHAT_IMAGE_EXTENSIONS


def _model_list(raw: str) -> List[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def _prepare_image(file_bytes: bytes) -> Tuple[str, int, int]:
    """Validate the image and return (data URI, width, height), downscaled for the vision API."""
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(file_bytes)) as source:
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions exceed the supported image size.")
            image = ImageOps.exif_transpose(source)
            if image.mode in ("RGBA", "LA", "P"):
                # Flatten transparency onto white so dark-mode screenshots stay legible.
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.split()[-1])
            else:
                image = image.convert("RGB")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable image.") from exc

    if max(image.size) > MAX_VISION_SIDE:
        image.thumbnail((MAX_VISION_SIDE, MAX_VISION_SIDE))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    mime = "image/png"
    if buffer.tell() > MAX_VISION_PAYLOAD_BYTES:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        mime = "image/jpeg"
    data_uri = f"data:{mime};base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return data_uri, width, height


def _call_vision_models(data_uri: str) -> Tuple[Optional[str], Optional[str]]:
    """Try each configured vision model in order; return (analysis text, model id) or (None, None)."""
    from openai import OpenAI

    timeout = float(settings.VISION_TIMEOUT_SEC)
    providers = [
        (
            "groq",
            (settings.GROQ_API_KEY or "").strip(),
            "https://api.groq.com/openai/v1",
            _model_list(settings.VISION_GROQ_MODELS),
            {},
        ),
        (
            "openrouter",
            (settings.OPENROUTER_API_KEY or settings.LLM_API_KEY or "").strip(),
            "https://openrouter.ai/api/v1",
            _model_list(settings.VISION_OPENROUTER_MODELS),
            {"HTTP-Referer": "https://clyptus.ai", "X-Title": "Clyptus.AI"},
        ),
    ]
    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_USER_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ]

    for provider, api_key, base_url, models, headers in providers:
        if not api_key or not models:
            continue
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
                default_headers=headers or None,
            )
        except Exception as exc:
            logger.warning("[Vision: %s] Client initialization failed: %s", provider, exc)
            continue
        for model in models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2048,
                )
                content = (response.choices[0].message.content or "") if response.choices else ""
                content = _THINK_RE.sub("", content).strip()
                if content:
                    logger.info("[Vision: %s] Image analysed with model %s", provider, model)
                    return content, model
                logger.warning("[Vision: %s] Model %s returned empty content.", provider, model)
            except Exception as exc:
                logger.warning("[Vision: %s] Model %s failed (%s).", provider, model, str(exc)[:160])
    return None, None


def _split_detected_question(analysis: str) -> Tuple[str, Optional[str]]:
    """Remove the DETECTED_QUESTION marker line and return (analysis body, question or None)."""
    match = _DETECTED_RE.search(analysis)
    question = None
    if match:
        candidate = match.group(1).strip().strip('"').strip()
        if candidate and candidate.upper().rstrip(".") not in ("NONE", "N/A"):
            question = candidate[:500]
        analysis = _DETECTED_RE.sub("", analysis).strip()
    return analysis, question


def _ocr_text(filename: str, file_bytes: bytes) -> Optional[str]:
    """OCR lines only (without the extractor's header), or None when OCR finds nothing."""
    try:
        extracted = extract_document(filename, file_bytes)
    except ValueError as exc:
        logger.info("OCR found no usable text in '%s': %s", Path(filename).name, exc)
        return None
    lines = extracted.get("text", "").splitlines()
    body = "\n".join(lines[2:]) if len(lines) > 2 and lines[0].startswith("Image:") else "\n".join(lines)
    return body.strip() or None


def analyze_chat_image(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Read a chat image attachment. Returns the same shape as extract_document plus
    `detected_question` and `analysis_method` ("vision", "vision+ocr" or "ocr").
    """
    name = Path(filename).name
    ext = Path(filename).suffix.lower().lstrip(".")
    data_uri, width, height = _prepare_image(file_bytes)

    analysis, model = (None, None)
    if settings.VISION_ENABLED:
        analysis, model = _call_vision_models(data_uri)
    ocr = _ocr_text(filename, file_bytes)

    detected_question = None
    sections = [f"Image: {name} ({width} x {height} pixels)"]
    if analysis:
        body, detected_question = _split_detected_question(analysis)
        sections.append("AI image analysis:\n" + body)
        if ocr:
            sections.append("## OCR Cross-check (exact characters detected by OCR)\n" + ocr)
        method = "vision+ocr" if ocr else "vision"
    elif ocr:
        sections.append("OCR text in approximate top-to-bottom, left-to-right reading order:\n" + ocr)
        method = "ocr"
    else:
        raise ValueError(
            f"Could not read image '{name}': the image analysis service is unavailable "
            "and no readable text was detected."
        )

    text = clean_extracted_text("\n\n".join(sections))[:MAX_CHARACTERS_PER_DOCUMENT]
    logger.info("Chat image '%s' read via %s%s", name, method, f" ({model})" if model else "")
    return {
        "filename": name,
        "file_type": ext,
        "size_bytes": len(file_bytes),
        "page_count": 1,
        "char_count": len(text),
        "preview": text[:300] + ("..." if len(text) > 300 else ""),
        "text": text,
        "pages": [{"page": 1, "text": text, "char_count": len(text)}],
        "detected_question": detected_question,
        "analysis_method": method,
    }
