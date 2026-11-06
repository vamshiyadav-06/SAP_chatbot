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
        # Which regeneration of the question this answer is (the "Regeneration #N" badge). The provider
        # and model that wrote it are model names, so they stay admin-only.
        "regeneration_count": event.get("regeneration_count") or 0,
    }
    if event.get("verification_status") == "unavailable":
        payload["verification_status"] = "unavailable"
    # Token estimates only (used, generic-chatbot baseline, saved); no model or provider names.
    usage = event.get("token_usage")
    if isinstance(usage, dict):
        payload["token_usage"] = {key: int(usage.get(key) or 0) for key in ("used", "baseline", "saved")}
        payload["token_usage"]["cost"] = float(usage.get("cost") or 0)
    # The user's own free-token balance after this answer.
    if isinstance(event.get("token_balance"), (int, float)):
        payload["token_balance"] = float(event["token_balance"])
    return payload
