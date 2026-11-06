"""Answer language (Settings): a user asks in their selected language or English and gets answers in the
selected language.

* Low (direct) answers: the model is told to write the whole answer in the language.
* High (verified) answers: grounding checks compare English words against English SAP documentation, so the
  verified draft stays English and only the finished answer is translated (citation markers kept).
* Questions in another language are translated to English first, because the SAP-topic check and the
  retrieval work on English. The user's original wording is what is stored in the chat.
* Any translation failure falls back to the original text: a user always gets an answer.
"""

import contextvars
import logging
import re
from typing import Dict, Iterable, Iterator, Optional, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")

DEFAULT_LANGUAGE = "en"
# code -> (English name, native name)
LANGUAGES: Dict[str, tuple] = {
    "en": ("English", "English"),
    "hi": ("Hindi", "हिन्दी"),
    "te": ("Telugu", "తెలుగు"),
    "ta": ("Tamil", "தமிழ்"),
    "kn": ("Kannada", "ಕನ್ನಡ"),
    "ml": ("Malayalam", "മലയാളം"),
    "mr": ("Marathi", "मराठी"),
    "bn": ("Bengali", "বাংলা"),
    "gu": ("Gujarati", "ગુજરાતી"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ"),
    "ur": ("Urdu", "اردو"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "de": ("German", "Deutsch"),
    "pt": ("Portuguese", "Português"),
    "it": ("Italian", "Italiano"),
    "nl": ("Dutch", "Nederlands"),
    "ar": ("Arabic", "العربية"),
    "zh": ("Chinese (Simplified)", "简体中文"),
    "ja": ("Japanese", "日本語"),
    "ko": ("Korean", "한국어"),
    "ru": ("Russian", "Русский"),
    "tr": ("Turkish", "Türkçe"),
    "id": ("Indonesian", "Bahasa Indonesia"),
}

_ENGLISH_HINTS = re.compile(
    r"\b(the|is|are|what|how|why|when|where|which|can|does|do|to|of|in|for|and|with|a|an|my|our|i|we|please|explain)\b",
    re.I,
)


def normalize(code: Optional[str]) -> str:
    code = (code or "").strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def english_name(code: str) -> str:
    return LANGUAGES[normalize(code)][0]


def is_english(code: Optional[str]) -> bool:
    return normalize(code) == DEFAULT_LANGUAGE


def looks_english(text: str) -> bool:
    """Plain ASCII text with common English words needs no translation (SAP terms alone do not count)."""
    text = text or ""
    if any(ord(ch) > 127 for ch in text if ch.isalpha()):
        return False
    return len(_ENGLISH_HINTS.findall(text)) >= 1


def _complete(prompt: str, system: str) -> Optional[str]:
    from backend.app.services.llm_service import llm_service  # avoid an import cycle

    try:
        reply = llm_service.generate_completion(prompt, system)
    except Exception as exc:
        logger.warning("Translation call failed (%s)", type(exc).__name__)
        return None
    reply = (reply or "").strip()
    return reply or None


def question_to_english(question: str, language: str) -> str:
    """The question in English for the SAP-topic check and retrieval; the original on any failure."""
    if is_english(language) or not question.strip() or looks_english(question):
        return question
    translated = _complete(
        f"Translate this question to English. Reply with the translation only, no quotes or notes. Keep SAP "
        f"transaction codes, table and field names, product names and abbreviations (SAP BRIM, FI-CA, SOM, CC, CI) "
        f"unchanged.\n\n{question}",
        "You are a precise technical translator for SAP documentation.",
    )
    return translated if translated and len(translated) <= max(2000, len(question) * 6) else question


def answer_to_language(answer: str, language: str) -> str:
    """A finished (English) answer written in the user's language; the original on any failure."""
    if is_english(language) or not answer.strip():
        return answer
    translated = _complete(
        f"Translate the following answer into {english_name(language)}. Keep the Markdown structure exactly "
        f"(headings, lists, tables, bold, code blocks). Do not translate or change: SAP transaction codes, table "
        f"and field names, program and class names, code, URLs, product names and abbreviations, or citation "
        f"markers such as [E1] or [E2][E3]. Reply with the translation only.\n\n{answer}",
        "You are a precise technical translator for SAP documentation. You never add, remove or change facts.",
    )
    return translated or answer


# --- prompt directive for direct (Low) answers ------------------------------------------------------

_active: contextvars.ContextVar[str] = contextvars.ContextVar("answer_language", default=DEFAULT_LANGUAGE)


def scoped(events: Iterable[T], language: str) -> Iterator[T]:
    """Steps `events` with the answer language active (set around every step, as token_meter does)."""
    iterator = iter(events)
    language = normalize(language)
    while True:
        token = _active.set(language)
        try:
            item = next(iterator)
        except StopIteration:
            return
        finally:
            _active.reset(token)
        yield item


def prompt_block() -> str:
    language = _active.get()
    if is_english(language):
        return ""
    name = english_name(language)
    return (
        f"ANSWER LANGUAGE: The user reads {name}. Write the whole answer in {name}, even if the question or the "
        f"retrieved text is in another language. Keep SAP transaction codes, table and field names, code, product "
        f"names and abbreviations (SAP BRIM, FI-CA, SOM, CC, CI) in their original form."
    )
