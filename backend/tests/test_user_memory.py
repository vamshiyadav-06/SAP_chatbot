"""Permanent user memory ("save it"): commands, storage, use in every chat, privacy, and management."""

import importlib

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.user_memory import UserMemory
from backend.app.services import user_memory
from backend.tests.org_helpers import OrgFixtures, headers_for

client = TestClient(app)
llm_module = importlib.import_module("backend.app.services.llm_service")


@pytest.fixture
def fx():
    fixtures = OrgFixtures()
    yield fixtures
    fixtures.cleanup()


@pytest.mark.parametrize("text", ["save it", "Save this.", "please remember this permanently", "ok save that to memory",
                                  "train on that", "Save"])
def test_save_it_commands_refer_to_the_previous_message(text):
    assert user_memory.parse_command(text) == ("implicit", None)


@pytest.mark.parametrize("text,saved", [
    ("remember that I run S/4HANA 2023 on premise", "I run S/4HANA 2023 on premise"),
    ("Remember: our billing runs nightly", "our billing runs nightly"),
    ("save to memory: my name is Ravi", "my name is Ravi"),
])
def test_remember_that_commands_carry_their_own_text(text, saved):
    assert user_memory.parse_command(text) == ("explicit", saved)


@pytest.mark.parametrize("text", ["what is FI-CA?", "remember when we talked about X?", "save the invoice as pdf",
                                  "keep it short", "How do I save a billing document?"])
def test_ordinary_questions_are_not_save_commands(text):
    assert user_memory.parse_command(text) is None


def test_save_it_stores_what_the_user_just_gave_and_every_chat_can_use_it(fx):
    user = fx.user()
    history = [{"role": "user", "content": "Our company is Acme; we bill 2M subscriptions a month in BRIM."},
               {"role": "assistant", "content": "Understood."}]
    with SessionLocal() as db:
        reply = user_memory.handle_command(db, user.id, "chat-a", "save it", history)
        assert reply.startswith("Saved to your memory")
        again = user_memory.handle_command(db, user.id, "chat-a", "save it", history)
        assert again.startswith("I already have this saved")
        assert db.query(UserMemory).filter(UserMemory.user_id == user.id).count() == 1  # no duplicates

        text = user_memory.prompt_text(db, user.id, "How many subscriptions do we bill?")
    assert "Acme" in text

    # A different chat of the same user: the prompt carries the memory, as the user's own statement.
    def build_prompt():  # built lazily, as the real streams do, while the memory is active
        yield llm_module.llm_service._build_sprint_prompt("What is our billing volume?", [], None)

    with_memory = list(user_memory.scoped(build_prompt(), text))[0]
    assert "USER'S SAVED MEMORY" in with_memory and "Acme" in with_memory
    assert "Acme" not in llm_module.llm_service._build_sprint_prompt("What is our billing volume?", [], None)


def test_a_question_and_its_answer_are_saved_together(fx):
    user = fx.user()
    history = [{"role": "user", "content": "What is a billable item?"},
               {"role": "assistant", "content": "A billable item is a charge ready for invoicing."}]
    with SessionLocal() as db:
        user_memory.handle_command(db, user.id, "c", "save this", history)
        saved = user_memory.list_memories(db, user.id)[0].content
    assert saved.startswith("Question: What is a billable item?") and "ready for invoicing" in saved


def test_nothing_to_save_is_said_plainly(fx):
    user = fx.user()
    with SessionLocal() as db:
        assert "nothing to save" in user_memory.handle_command(db, user.id, "c", "save it", []).lower()
        assert user_memory.list_memories(db, user.id) == []


def test_memories_are_private_to_their_user(fx):
    owner, other = fx.user(), fx.user()
    with SessionLocal() as db:
        user_memory.handle_command(db, owner.id, "c", "remember that my secret codename is Falcon", [])
        assert user_memory.prompt_text(db, other.id, "codename") == ""
    assert client.get("/api/memories", headers=headers_for(other.id)).json() == []
    item = client.get("/api/memories", headers=headers_for(owner.id)).json()[0]
    assert client.delete(f"/api/memories/{item['id']}", headers=headers_for(other.id)).status_code == 404


def test_the_user_can_list_and_delete_memories(fx):
    user = fx.user()
    headers = headers_for(user.id)
    with SessionLocal() as db:
        user_memory.handle_command(db, user.id, "c", "remember that I prefer short answers", [])
        user_memory.handle_command(db, user.id, "c", "remember that we use Convergent Invoicing", [])
    items = client.get("/api/memories", headers=headers).json()
    assert [m["content"] for m in items] == ["we use Convergent Invoicing", "I prefer short answers"]
    assert client.delete(f"/api/memories/{items[0]['id']}", headers=headers).status_code == 204
    assert len(client.get("/api/memories", headers=headers).json()) == 1
    assert client.delete("/api/memories", headers=headers).status_code == 204
    assert client.get("/api/memories", headers=headers).json() == []


def test_a_long_memory_list_is_trimmed_to_the_best_matches_for_the_question(fx, monkeypatch):
    user = fx.user()
    monkeypatch.setattr(user_memory, "PROMPT_BUDGET_CHARS", 120)
    with SessionLocal() as db:
        user_memory.save_memory(db, user.id, "The dunning run happens every Monday at 06:00 for all contract accounts.")
        user_memory.save_memory(db, user.id, "Our favourite colour is blue and we like hiking on weekends a lot.")
        text = user_memory.prompt_text(db, user.id, "when is the dunning run")
    assert "dunning" in text and "colour" not in text


def test_a_save_command_in_a_chat_is_confirmed_without_the_model_and_stored(fx):
    user = fx.user()
    headers = headers_for(user.id)
    chat = client.post("/api/chats", headers=headers, json={"title": "t"}).json()
    response = client.post(f"/api/chats/{chat['id']}/messages?stream=true", headers=headers,
                           json={"content": "remember that I work on SAP BRIM billing at Acme", "mode": "sprint"})
    assert response.status_code == 200, response.text
    assert "Saved to your memory" in response.text
    memories = client.get("/api/memories", headers=headers).json()
    assert [m["content"] for m in memories] == ["I work on SAP BRIM billing at Acme"]
