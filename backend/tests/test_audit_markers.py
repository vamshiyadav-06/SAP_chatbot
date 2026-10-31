"""AUDIT_REPORT F-38: evidence markers ([E#], legacy [KB_n]/[WEB_n]/[REPO_n]) never reach regular users."""

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.api import rag as rag_api
from backend.app.database import get_db
from backend.app.main import app
from backend.app.security.auth import get_current_user
from backend.app.services.evidence_markers import StreamingMarkerStripper, strip_markers

ANSWER = "Posting [E1] works [KB_2] here [[E3] and [WEB_10]. Arrays [a] stay [E4, E5] [REPO_7]."
LEAK = re.compile(r"E\d|KB_\d|WEB_\d|REPO_\d")


@pytest.mark.parametrize("size", [1, 2, 3, 5, 8, 64])
def test_streaming_stripper_removes_split_and_legacy_markers(size):
    stripper = StreamingMarkerStripper()
    out = "".join(stripper.feed(ANSWER[i:i + size]) for i in range(0, len(ANSWER), size)) + stripper.flush()
    assert not LEAK.search(out), out
    assert "[a]" in out, "ordinary bracketed text is kept"


def test_strip_markers_removes_legacy_markers():
    assert not LEAK.search(strip_markers(ANSWER))


def test_rag_stream_endpoint_never_sends_markers_to_regular_user(monkeypatch):
    def fake_stream(*args, **kwargs):
        for i in range(0, len(ANSWER), 3):
            yield {"type": "token", "content": ANSWER[i:i + 3]}
        yield {"type": "done", "answer": ANSWER, "source_type": "knowledge_base", "grounding_score": 0.9,
               "citations": [{"document": "x"}], "follow_up_questions": []}

    monkeypatch.setattr(rag_api.rag_service, "stream_query", fake_stream)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1", is_admin=False, role="consultant")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as client:
        response = client.post("/api/rag/query/stream", json={"query": "How is the posting area configured?"},
                               headers={"Authorization": "Bearer f38-test"})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    done = events[-1]
    assert not LEAK.search(streamed), streamed
    assert not LEAK.search(done["answer"]) and not done.get("citations")


INTERNAL_KEYS = {"diagnostics", "model_used", "provider_used", "shadow_audit", "validation_audit", "answer_decision",
                 "kb_score", "web_score", "winning_score", "source_scores", "comparison_audit", "selected_source",
                 "internal_evidence_confidence", "selected_evidence_quality", "selection_summary", "failed_over",
                 "regeneration_count", "grounded_score", "is_in_rag_pipeline", "route"}


def test_public_done_event_is_an_allowlist():
    from backend.app.services.public_payload import public_done_event
    internal = {key: "secret" for key in INTERNAL_KEYS}
    event = public_done_event({"type": "done", "answer": "A [E1].", "message_id": "m1", **internal,
                               "images": [{"url": "u", "source_url": "s", "source_title": "t"}]})
    assert not INTERNAL_KEYS & set(event)
    assert event["answer"] == "A." and event["message_id"] == "m1"
    assert event["images"][0]["source_url"] is None and event["images"][0]["source_title"] is None


def test_rag_stream_done_hides_diagnostics_and_model_names_from_regular_user(monkeypatch):
    def fake_stream(*args, **kwargs):
        yield {"type": "token", "content": "ok"}
        yield {"type": "done", "answer": "ok", **{key: "secret" for key in INTERNAL_KEYS}}

    monkeypatch.setattr(rag_api.rag_service, "stream_query", fake_stream)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u2", is_admin=False, role="consultant")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as client:
        response = client.post("/api/rag/query/stream", json={"query": "q"}, headers={"Authorization": "Bearer f27-test"})
    done = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")][-1]
    assert done["type"] == "done" and not INTERNAL_KEYS & set(done)
