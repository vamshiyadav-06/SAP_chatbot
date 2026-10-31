"""AUDIT_REPORT F-37: save-partial needs a server-issued stream id; interrupted answers cannot be shared."""

import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api import messages as messages_api
from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.user import User
from backend.app.security.auth import create_access_token, hash_password
from backend.app.security.stream_tokens import issue_stream_token, verify_stream_token


@pytest.fixture(scope="module")
def owner_chat():
    init_db()
    db = SessionLocal()
    users = [User(email=f"partial_{uuid.uuid4().hex[:8]}@example.com", name="Partial", is_admin=False,
                  password_hash=hash_password(uuid.uuid4().hex), role="consultant") for _ in range(2)]
    db.add_all(users)
    db.flush()
    chats = [Chat(user_id=u.id, title="Partial test") for u in users]
    db.add_all(chats)
    db.commit()
    yield db, users, chats
    db.query(User).filter(User.id.in_([u.id for u in users])).delete(synchronize_session=False)
    db.commit()
    db.close()


def headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.id, 'ver': user.token_version})}"}


def save(client, user, chat, stream_id, content="Partial answer the user saw"):
    body = {"content": content}
    if stream_id is not None:
        body["stream_id"] = stream_id
    return client.post(f"/api/chats/{chat.id}/messages/save-partial", json=body, headers=headers(user))


def test_stream_tokens_are_bound_to_user_chat_and_expiry():
    token = issue_stream_token("u1", "c1")
    assert verify_stream_token(token, "u1", "c1")
    assert verify_stream_token(token, "u2", "c1") is None
    assert verify_stream_token(token, "u1", "c2") is None
    assert verify_stream_token(token[:-2] + "xx", "u1", "c1") is None
    assert verify_stream_token("not-a-token", "u1", "c1") is None
    with patch("backend.app.security.stream_tokens.time.time", return_value=time.time() + 3 * 3600):
        assert verify_stream_token(token, "u1", "c1") is None


def test_save_partial_rejects_missing_forged_and_foreign_stream_ids(owner_chat):
    _, (alice, bob), (alice_chat, bob_chat) = owner_chat
    with TestClient(app) as client:
        assert save(client, alice, alice_chat, None).status_code == 422
        assert save(client, alice, alice_chat, "x" * 40).status_code == 403
        bobs_token = issue_stream_token(bob.id, bob_chat.id)
        assert save(client, alice, alice_chat, bobs_token).status_code == 403
        other_chat_token = issue_stream_token(alice.id, bob_chat.id)
        assert save(client, alice, alice_chat, other_chat_token).status_code == 403


def test_save_partial_accepts_a_valid_stream_id_once(owner_chat):
    db, (alice, _), (alice_chat, _) = owner_chat
    token = issue_stream_token(alice.id, alice_chat.id)
    with TestClient(app) as client:
        first = save(client, alice, alice_chat, token)
        second = save(client, alice, alice_chat, token)
    assert first.status_code == 200 and second.status_code == 409
    stored = db.query(Message).filter(Message.id == first.json()["message_id"]).one()
    assert stored.source_type == "interrupted" and stored.role == "assistant"


def test_interrupted_answer_cannot_be_shared(owner_chat):
    db, (alice, _), (alice_chat, _) = owner_chat
    db.add(Message(chat_id=alice_chat.id, role="user", content="Question?"))
    db.commit()
    token = issue_stream_token(alice.id, alice_chat.id)
    with TestClient(app) as client:
        saved = save(client, alice, alice_chat, token, content="Forged official-looking answer")
        resp = client.post(f"/api/chats/{alice_chat.id}/messages/{saved.json()['message_id']}/share", headers=headers(alice))
    assert resp.status_code == 409


def test_stream_starts_with_a_token_for_this_user_and_chat():
    def one_done(*args, **kwargs):
        yield {"type": "done", "answer": "ok"}

    user = SimpleNamespace(id="u-stream", is_admin=False)
    save_db = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    with patch.object(messages_api, "SessionLocal", return_value=save_db), \
            patch.object(messages_api.rag_service, "stream_query", side_effect=one_done):
        response = messages_api.handle_streaming_response("chat-x", "q", chat_history=[], current_user=user)
        import asyncio

        async def first_event():
            async for chunk in response.body_iterator:
                return chunk if isinstance(chunk, str) else chunk.decode()
        event = json.loads(asyncio.run(first_event())[6:])
    assert event["type"] == "stream"
    assert verify_stream_token(event["stream_id"], "u-stream", "chat-x")
