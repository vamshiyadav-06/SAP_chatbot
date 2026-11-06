"""Token savings are stored with each streamed answer, returned with the chat history (so the badge survives
a reload) and summed per account for the Settings total (owner decision 2026-11-04, token savings "B")."""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.app.api import messages as messages_api
from backend.app.database import SessionLocal, engine, run_migrations
from backend.app.main import app
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.user import User
from backend.app.services.conversation_memory_service import conversation_memory_service
from backend.tests.offline_rag import DEFAULT_ANSWER, RAG_QUESTION, offline_rag
from backend.tests.test_chat_modes import FakeSession, _sse_events
from backend.tests.test_token_savings import _fake_sprint_stream

client = TestClient(app)
PASSWORD = "Password123!"


# ---------------------------------------------------------------- stored with each streamed answer

def test_sprint_answer_stores_its_token_usage(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(messages_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(messages_api, "issue_stream_token", lambda *_args: "signed-stream")
    monkeypatch.setattr(messages_api.llm_service, "stream_sprint_reply", _fake_sprint_stream)
    monkeypatch.setattr(conversation_memory_service, "update_rolling_summary", lambda *_a, **_k: None)
    events = _sse_events(messages_api.handle_sprint_streaming_response(
        "chat-id", "Explain SAP BRIM", chat_history=[], current_user=SimpleNamespace(id="u", is_admin=False),
        attachments=[], user_message_id="user-message-id", conversation_chars=40000,
    ))

    usage = events[-1]["token_usage"]
    answer = next(row for row in session.added if isinstance(row, Message) and row.role == "assistant")
    assert (answer.tokens_used, answer.tokens_baseline) == (usage["used"], usage["baseline"])
    assert usage["saved"] > 0


def test_scholar_answer_stores_its_token_usage():
    def metered_generate(query, evidence, source_type="knowledge_base", **kwargs):
        from backend.app.services import token_meter
        token_meter.stage_prompt("p" * 1200, "s" * 400)
        token_meter.record_reply(DEFAULT_ANSWER)
        return DEFAULT_ANSWER

    session = MagicMock()

    async def collect(response):
        return [chunk async for chunk in response.body_iterator]

    with offline_rag(), \
            patch("backend.app.services.rag_service.llm_service.generate_answer", side_effect=metered_generate), \
            patch.object(messages_api, "SessionLocal", return_value=session), \
            patch.object(conversation_memory_service, "embed_message_content", return_value=None), \
            patch.object(conversation_memory_service, "update_rolling_summary", return_value=None):
        response = messages_api.handle_streaming_response(
            "chat-1", RAG_QUESTION, chat_history=[], current_user=SimpleNamespace(id="u1", is_admin=False),
            user_message_id="m1", conversation_chars=0,
        )
        body = "".join(c if isinstance(c, str) else c.decode() for c in asyncio.run(collect(response)))

    done = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")][-1]
    assert done["type"] == "done", done
    stored = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], Message)]
    assert stored, "the answer was persisted"
    assert (stored[0].tokens_used, stored[0].tokens_baseline) == (
        done["token_usage"]["used"], done["token_usage"]["baseline"]
    )


# ---------------------------------------------------------------- history and account totals (real test DB)

def _account(label: str):
    email = f"tokens_{label}_{uuid.uuid4().hex[:8]}@example.com"
    assert client.post("/api/auth/register", json={"email": email, "name": "Token User", "password": PASSWORD}).status_code == 201
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()
    return login["user"]["id"], {"Authorization": f"Bearer {login['access_token']}"}


def _chat_with(user_id: str, answers):
    """A chat with one question per answer; `answers` holds (tokens_used, tokens_baseline), None = unknown."""
    db = SessionLocal()
    try:
        chat = Chat(user_id=user_id, title="Token savings")
        db.add(chat)
        db.flush()
        for used_baseline in answers:
            db.add(Message(chat_id=chat.id, role="user", content="What is FI-CA?"))
            db.flush()
            used, baseline = used_baseline or (None, None)
            db.add(Message(chat_id=chat.id, role="assistant", content="FI-CA is ...",
                           tokens_used=used, tokens_baseline=baseline))
            db.flush()
        db.commit()
        return chat.id
    finally:
        db.close()


def _delete_users(*user_ids):
    """Chats and their messages go with the user (ON DELETE CASCADE)."""
    db = SessionLocal()
    try:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_history_returns_each_answers_stored_savings():
    user_id, headers = _account("history")
    try:
        chat_id = _chat_with(user_id, [(100, 400), None])
        messages = client.get(f"/api/chats/{chat_id}/messages", headers=headers).json()
        answers = [m for m in messages if m["role"] == "assistant"]
        assert answers[0]["token_usage"] == {"used": 100, "baseline": 400, "saved": 300, "cost": 0.017}
        assert answers[1]["token_usage"] is None, "older answers have no figures; nothing is guessed"
        assert all(m["token_usage"] is None for m in messages if m["role"] == "user")
    finally:
        _delete_users(user_id)


def test_account_total_sums_only_your_own_answers():
    user_a, headers_a = _account("a")
    user_b, headers_b = _account("b")
    try:
        _chat_with(user_a, [(100, 400), (50, 40), None])  # the second saved nothing: it counts 0, not -10
        _chat_with(user_a, [(10, 110)])
        _chat_with(user_b, [(1, 9999)])

        assert client.get("/api/auth/me/token-savings", headers=headers_a).json() == {
            "answers": 3, "used": 160, "baseline": 550, "saved": 400,
        }
        assert client.get("/api/auth/me/token-savings", headers=headers_b).json()["saved"] == 9998
        assert client.get("/api/auth/me/token-savings").status_code == 401
    finally:
        _delete_users(user_a, user_b)


def test_a_new_account_has_saved_nothing_yet():
    user_id, headers = _account("new")
    try:
        assert client.get("/api/auth/me/token-savings", headers=headers).json() == {
            "answers": 0, "used": 0, "baseline": 0, "saved": 0,
        }
    finally:
        _delete_users(user_id)


def test_migration_0008_adds_the_token_columns_idempotently():
    run_migrations()
    run_migrations()
    columns = {column["name"] for column in inspect(engine).get_columns("messages")}
    assert {"tokens_used", "tokens_baseline"} <= columns
