"""
What a regular (non-admin) user may receive at the end of a streamed answer.

An allowlist, not a denylist: any field the RAG pipeline adds later (diagnostics, model names,
shadow audits, scores) stays admin-only unless it is added here on purpose.
"""

from typing import Any, Dict

from backend.app.services.evidence_markers import strip_markers


def public_done_event(event: Dict[str, Any]) -> Dict[str, Any]:
    images = [
        {
            "url": img.get("url"),
            "description": img.get("description"),
            "alt_text": img.get("alt_text"),
            "source_url": None,
            "source_title": None,
        }
        for img in (event.get("images") or [])
    ]
    payload = {
        "type": "done",
        "answer": strip_markers(event.get("answer", "")),
        "message_id": event.get("message_id"),
        "follow_up_questions": event.get("follow_up_questions") or [],
        "images": images,
        # Legacy keys kept with neutral values so existing clients keep working.
        "citations": [],
        "web_sources": [],
        "source_type": None,
        "grounding_score": None,
        "external_search_used": False,
    }
    if event.get("verification_status") == "unavailable":
        payload["verification_status"] = "unavailable"
    return payload
