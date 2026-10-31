import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal, init_db
from backend.app.main import app
from backend.app.models.message import Message

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _schema():
    # A module-level TestClient skips the app lifespan, so create the shared_prompts table here.
    init_db()


def _login(email: str) -> dict:
    client.post("/api/auth/register", json={"email": email, "name": "Prompt Sharer", "password": "Password123!"})
    token = client.post("/api/auth/login", json={"email": email, "password": "Password123!"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _add_message(chat_id: str, role: str, content: str) -> str:
    db = SessionLocal()
    try:
        msg = Message(chat_id=chat_id, role=role, content=content)
        db.add(msg)
        db.commit()
        return msg.id
    finally:
        db.close()


def test_shared_prompt_is_public_and_hides_attachment_names():
    headers = _login("prompt_sharer@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Share test"}, headers=headers).json()["id"]
    msg_id = _add_message(chat_id, "user", "[Attached: payroll_2026.pdf (3 pages)]\n\nHow do I reverse a billing document?")

    first = client.post(f"/api/chats/{chat_id}/messages/{msg_id}/share", headers=headers)
    assert first.status_code == 200, first.text
    token = first.json()["token"]
    assert len(token) >= 16

    # Sharing the same prompt again keeps the same link.
    assert client.post(f"/api/chats/{chat_id}/messages/{msg_id}/share", headers=headers).json()["token"] == token

    public = client.get(f"/api/shared/prompts/{token}")  # no auth header
    assert public.status_code == 200
    assert public.json()["content"] == "How do I reverse a billing document?"
    assert "payroll_2026" not in public.text


def test_share_prompt_rejects_other_users_and_unknown_tokens():
    owner = _login("share_owner@sap.com")
    intruder = _login("share_intruder@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Owned"}, headers=owner).json()["id"]
    user_id = _add_message(chat_id, "user", "Private question")
    answer_id = _add_message(chat_id, "assistant", "Private answer")

    assert client.post(f"/api/chats/{chat_id}/messages/{user_id}/share", headers=intruder).status_code == 404
    assert client.post(f"/api/chats/{chat_id}/messages/{answer_id}/share", headers=intruder).status_code == 404
    assert client.get("/api/shared/prompts/not-a-real-token").status_code == 404


def test_shared_answer_includes_its_question_without_evidence_markers():
    headers = _login("answer_sharer@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Answer share"}, headers=headers).json()["id"]
    _add_message(chat_id, "user", "[Attached: secret.pdf (1 pages)]\n\nWhat is FI-CA?")
    answer_id = _add_message(chat_id, "assistant", "FI-CA is Contract Accounting [E1].")

    resp = client.post(f"/api/chats/{chat_id}/messages/{answer_id}/share", headers=headers)
    assert resp.status_code == 200, resp.text

    public = client.get(f"/api/shared/prompts/{resp.json()['token']}").json()
    assert public["content"] == "What is FI-CA?"
    assert public["answer"] == "FI-CA is Contract Accounting."
    assert "secret.pdf" not in str(public)


def test_concurrent_shares_of_one_message_return_the_same_link():
    # React StrictMode opens the share dialog's effect twice, so two requests race in dev.
    from concurrent.futures import ThreadPoolExecutor

    headers = _login("race_sharer@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Race"}, headers=headers).json()["id"]
    msg_id = _add_message(chat_id, "user", "Same prompt, two clicks")
    url = f"/api/chats/{chat_id}/messages/{msg_id}/share"

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url, headers=headers), range(4)))

    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["token"] for r in responses}) == 1


def test_feedback_is_saved_cleared_and_limited_to_owned_answers():
    owner = _login("feedback_owner@sap.com")
    intruder = _login("feedback_intruder@sap.com")
    chat_id = client.post("/api/chats", json={"title": "Feedback"}, headers=owner).json()["id"]
    question_id = _add_message(chat_id, "user", "Question")
    answer_id = _add_message(chat_id, "assistant", "Answer")
    url = f"/api/chats/{chat_id}/messages/{answer_id}/feedback"

    assert client.put(url, json={"value": "up"}, headers=owner).json()["feedback"] == "up"
    stored = client.get(f"/api/chats/{chat_id}/messages", headers=owner).json()
    assert next(m for m in stored if m["id"] == answer_id)["feedback"] == "up"

    assert client.put(url, json={"value": None}, headers=owner).json()["feedback"] is None
    assert client.put(url, json={"value": "meh"}, headers=owner).status_code == 422
    assert client.put(url, json={"value": "down"}, headers=intruder).status_code == 404
    question_url = f"/api/chats/{chat_id}/messages/{question_id}/feedback"
    assert client.put(question_url, json={"value": "up"}, headers=owner).status_code == 404
