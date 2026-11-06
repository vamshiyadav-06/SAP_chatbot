"""Chat create/get/update responses carry chat metadata only.

They used to embed every message through ``MessageResponse``: that exposed the answering provider/model,
source type, grounding score and raw evidence markers that ``GET /chats/{id}/messages`` hides from regular
users, and a chat with a cited answer failed with 500 (the citation rows do not match ``CitationResponse``)
after PATCH had already committed the rename.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.chat import Chat
from backend.app.models.citation import Citation
from backend.app.models.message import Message
from backend.app.models.user import User
from backend.app.security.auth import hash_password

PASSWORD = "MetaPrivacy123!"
CHAT_KEYS = {"id", "user_id", "title", "project_id", "created_at", "updated_at"}
LEAK_MARKERS = ("llm_provider", "llm_model", "grounding_score", "source_type", "groq", "secret-model", "[E1]")


@pytest.fixture()
def cited_chat():
    email = f"chat_meta_{uuid.uuid4().hex[:10]}@example.com"
    db = SessionLocal()
    try:
        user = User(email=email, name="Meta User", password_hash=hash_password(PASSWORD), is_admin=False, role="consultant")
        db.add(user)
        db.commit()
        chat = Chat(user_id=user.id, title="Cited chat")
        db.add(chat)
        db.commit()
        db.add(Message(chat_id=chat.id, role="user", content="What is SAP BRIM?"))
        answer = Message(
            chat_id=chat.id, role="assistant", content="SAP BRIM bills usage [E1].", source_type="knowledge_base",
            grounding_score=0.91, llm_provider="groq", llm_model="secret-model",
        )
        db.add(answer)
        db.commit()
        db.add(Citation(
            message_id=answer.id, document_id="doc-brim.pdf", document_name="brim.pdf", chunk_id=str(uuid.uuid4()),
            page_number=3, similarity_score=0.88, citation_text="BRIM covers subscription billing.",
        ))
        db.commit()
        user_id, chat_id = user.id, chat.id
    finally:
        db.close()

    yield email, chat_id

    db = SessionLocal()
    try:
        db.query(Chat).filter(Chat.id == chat_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    finally:
        db.close()


def _headers(client, email):
    resp = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _assert_metadata_only(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == CHAT_KEYS
    for marker in LEAK_MARKERS:
        assert marker not in resp.text


def test_get_and_patch_of_a_chat_with_a_cited_answer_return_chat_metadata_only(cited_chat):
    email, chat_id = cited_chat
    client = TestClient(app)
    headers = _headers(client, email)

    _assert_metadata_only(client.get(f"/api/chats/{chat_id}", headers=headers))

    patched = client.patch(f"/api/chats/{chat_id}", json={"title": "Renamed"}, headers=headers)
    _assert_metadata_only(patched)
    assert patched.json()["title"] == "Renamed"

    # The messages themselves stay available through the endpoint that sanitises them.
    listed = client.get(f"/api/chats/{chat_id}/messages", headers=headers)
    assert listed.status_code == 200
    assert [m["role"] for m in listed.json()] == ["user", "assistant"]


def test_create_chat_returns_chat_metadata_only(cited_chat):
    email, _ = cited_chat
    client = TestClient(app)
    headers = _headers(client, email)

    created = client.post("/api/chats", json={"title": "Fresh"}, headers=headers)
    assert created.status_code == 201, created.text
    assert set(created.json()) == CHAT_KEYS
    db = SessionLocal()
    try:
        db.query(Chat).filter(Chat.id == created.json()["id"]).delete()
        db.commit()
    finally:
        db.close()
