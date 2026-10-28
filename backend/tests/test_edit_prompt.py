import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api import messages as messages_api
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.message import Message
from backend.app.models.uploaded_attachment import UploadedAttachment

client = TestClient(app)


def _login(email: str) -> dict:
    client.post("/api/auth/register", json={"email": email, "name": "Prompt Editor", "password": "Password123!"})
    token = client.post("/api/auth/login", json={"email": email, "password": "Password123!"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _events(response) -> list:
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def _seed_conversation(chat_id: str) -> dict:
    """Two turns; the first prompt carries an attached file."""
    base = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        first = Message(chat_id=chat_id, role="user", content="[Attached: spec.pdf (2 pages)]\n\nOld question", created_at=base)
        first.uploaded_attachments = [
            UploadedAttachment(name="spec.pdf", file_type="pdf", page_count=2, extracted_text="Spec body text")
        ]
        rows = [
            first,
            Message(chat_id=chat_id, role="assistant", content="Old answer", source_type="knowledge_base", created_at=base + timedelta(seconds=1)),
            Message(chat_id=chat_id, role="user", content="Follow-up", created_at=base + timedelta(seconds=2)),
            Message(chat_id=chat_id, role="assistant", content="Follow-up answer", source_type="knowledge_base", created_at=base + timedelta(seconds=3)),
        ]
        db.add_all(rows)
        db.commit()
        return {"first_id": first.id}
    finally:
        db.close()


def test_edit_prompt_replaces_question_drops_later_turns_and_streams_new_answer():
    headers = _login("prompt_editor@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Edit test"}, headers=headers).json()["id"]
    first_id = _seed_conversation(chat_id)["first_id"]

    calls = {}

    def fake_stream(db, query, chat_history=None, user=None, attachments=None):
        calls.update(query=query, chat_history=chat_history, attachments=attachments)
        yield {"type": "token", "content": "New answer"}
        yield {"type": "done", "answer": "New answer", "source_type": "knowledge_base", "grounding_score": 0.9,
               "citations": [], "web_sources": [], "images": []}

    with patch.object(messages_api.rag_service, "stream_query", side_effect=fake_stream):
        resp = client.post(f"/api/chats/{chat_id}/messages/{first_id}/edit", json={"content": "New question"}, headers=headers)

    assert resp.status_code == 200, resp.text
    events = _events(resp)
    assert events[0] == {"type": "user_message", "message_id": first_id}
    assert events[-1]["type"] == "done"

    # The answer is generated for the new prompt, with no history from the discarded turns,
    # and the file attached to the original prompt is still used.
    assert calls["query"] == "New question"
    assert calls["chat_history"] == []
    assert [a["name"] for a in calls["attachments"]] == ["spec.pdf"]

    stored = client.get(f"/api/chats/{chat_id}/messages", headers=headers).json()
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "[Attached: spec.pdf (2 pages)]\n\nNew question"),
        ("assistant", "New answer"),
    ]
    assert stored[0]["id"] == first_id


def test_edit_prompt_rejects_other_users_and_assistant_messages():
    owner = _login("prompt_owner@sap.com")
    intruder = _login("prompt_intruder@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Owned"}, headers=owner).json()["id"]
    first_id = _seed_conversation(chat_id)["first_id"]

    resp = client.post(f"/api/chats/{chat_id}/messages/{first_id}/edit", json={"content": "Hijack"}, headers=intruder)
    assert resp.status_code == 404

    assistant_id = next(m["id"] for m in client.get(f"/api/chats/{chat_id}/messages", headers=owner).json() if m["role"] == "assistant")
    resp = client.post(f"/api/chats/{chat_id}/messages/{assistant_id}/edit", json={"content": "Nope"}, headers=owner)
    assert resp.status_code == 404

    resp = client.post(f"/api/chats/{chat_id}/messages/{first_id}/edit", json={"content": "   "}, headers=owner)
    assert resp.status_code in (400, 422)
