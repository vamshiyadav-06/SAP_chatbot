import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal, init_db
from backend.app.models.user import User
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.services.conversation_memory_service import (
    conversation_memory_service,
    MemoryIntent,
    sanitize_for_memory,
)
from backend.app.services.rag_service import rag_service

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def registered_users():
    # User A
    user_a_email = "memory_tester_a@sap.com"
    client.post("/api/auth/register", json={"email": user_a_email, "name": "Memory User A", "password": "Password123!"})
    login_a = client.post("/api/auth/login", json={"email": user_a_email, "password": "Password123!"}).json()
    token_a = login_a["access_token"]
    user_a_id = login_a["user"]["id"]

    # User B
    user_b_email = "memory_tester_b@sap.com"
    client.post("/api/auth/register", json={"email": user_b_email, "name": "Memory User B", "password": "Password123!"})
    login_b = client.post("/api/auth/login", json={"email": user_b_email, "password": "Password123!"}).json()
    token_b = login_b["access_token"]
    user_b_id = login_b["user"]["id"]

    return {
        "user_a": {"id": user_a_id, "email": user_a_email, "token": token_a, "headers": {"Authorization": f"Bearer {token_a}"}},
        "user_b": {"id": user_b_id, "email": user_b_email, "token": token_b, "headers": {"Authorization": f"Bearer {token_b}"}},
    }


# ==============================================================================
# TEST 1: New conversation with fewer than 20 messages
# ==============================================================================
def test_1_conversation_with_fewer_than_20_messages(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Short Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        msg = Message(
            chat_id=chat.id,
            role=role,
            content=f"Message {i+1} content",
            created_at=base_time + timedelta(minutes=i)
        )
        db_session.add(msg)
    db_session.commit()

    recent = conversation_memory_service.get_recent_messages(db_session, chat.id, limit=20)
    assert len(recent) == 6
    assert recent[0]["content"] == "Message 1 content"
    assert recent[-1]["content"] == "Message 6 content"


# ==============================================================================
# TEST 2 & 3: Conversation with > 20 messages and order verification
# ==============================================================================
def test_2_and_3_conversation_with_more_than_20_messages(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Long Chat 30 Msgs")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        msg = Message(
            chat_id=chat.id,
            role=role,
            content=f"Sequential turn {i+1}",
            created_at=base_time + timedelta(minutes=i)
        )
        db_session.add(msg)
    db_session.commit()

    # Context window query
    recent = conversation_memory_service.get_recent_messages(db_session, chat.id, limit=20)
    assert len(recent) == 20
    # Must be the latest 20: turn 11 to turn 30
    assert recent[0]["content"] == "Sequential turn 11"
    assert recent[-1]["content"] == "Sequential turn 30"
    # Order must be strictly ascending (chronological)
    for idx in range(len(recent) - 1):
        num_curr = int(recent[idx]["content"].split()[-1])
        num_next = int(recent[idx+1]["content"].split()[-1])
        assert num_next == num_curr + 1


# ==============================================================================
# TEST 4: Older messages remain persisted after 20-message limit is exceeded
# ==============================================================================
def test_4_older_messages_persisted(db_session, registered_users):
    user = registered_users["user_a"]
    chat = db_session.query(Chat).filter(Chat.user_id == user["id"], Chat.title == "Long Chat 30 Msgs").first()
    assert chat is not None

    total_in_db = db_session.query(Message).filter(Message.chat_id == chat.id).count()
    assert total_in_db == 30, "All 30 messages must remain persisted in DB"

    # Messages 1 to 10 are still in the DB even though excluded from the 20 context window
    first_msg = db_session.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.asc()).first()
    assert first_msg.content == "Sequential turn 1"


# ==============================================================================
# TEST 5: Exact recall of the first question after 50 messages (MANDATORY)
# ==============================================================================
def test_5_exact_recall_of_first_question_after_50_messages(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="50 Message Deep Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(hours=5)
    first_question = "How do I configure Convergent Invoicing billing plans in SAP BRIM?"

    # First message: user
    db_session.add(Message(
        chat_id=chat.id,
        role="user",
        content=first_question,
        created_at=base_time
    ))
    db_session.add(Message(
        chat_id=chat.id,
        role="assistant",
        content="Billing plans in SAP CI define recurrence patterns...",
        created_at=base_time + timedelta(minutes=1)
    ))

    # Add 48 more messages (total 50)
    for i in range(2, 50):
        role = "user" if i % 2 == 0 else "assistant"
        db_session.add(Message(
            chat_id=chat.id,
            role=role,
            content=f"Subsequent discussion message #{i+1}",
            created_at=base_time + timedelta(minutes=i)
        ))
    db_session.commit()

    # 1. Deterministic DB lookup
    first_retrieved = conversation_memory_service.get_first_user_message(db_session, chat.id)
    assert first_retrieved is not None
    assert first_retrieved["content"] == first_question

    # 2. End-to-end RAG answer generation with mock LLM
    user_obj = db_session.query(User).filter(User.id == user["id"]).first()
    recent = conversation_memory_service.get_recent_messages(db_session, chat.id, limit=20)
    
    with patch("backend.app.services.llm_service.llm_service.generate_answer") as mock_gen:
        mock_gen.return_value = {
            "answer": f"Your first question in this chat was: '{first_question}'",
            "source_type": "conversation_memory",
            "grounding_score": 1.0,
            "citations": [],
            "web_sources": []
        }
        res = rag_service.process_query(
            db_session,
            "What was my first question in this chat?",
            chat_history=recent,
            user=user_obj,
            chat_id=chat.id
        )
        assert res["source_type"] == "conversation_memory"
        assert first_question in res["answer"]


# ==============================================================================
# TEST 6: Exact config value recall from an older message
# ==============================================================================
def test_6_config_value_recall_from_older_message(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Config Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(hours=3)
    config_msg = "We set the PostgreSQL port to 5434 for this SAP BRIM database cluster."
    
    db_session.add(Message(
        chat_id=chat.id,
        role="user",
        content=config_msg,
        embedding=conversation_memory_service.embed_message_content(config_msg),
        created_at=base_time
    ))
    db_session.add(Message(
        chat_id=chat.id,
        role="assistant",
        content="Noted, PostgreSQL port 5434 is recorded.",
        embedding=conversation_memory_service.embed_message_content("Noted, PostgreSQL port 5434 is recorded."),
        created_at=base_time + timedelta(minutes=1)
    ))

    # Push it past the 20-message window
    for i in range(25):
        role = "user" if i % 2 == 0 else "assistant"
        db_session.add(Message(
            chat_id=chat.id,
            role=role,
            content=f"Ongoing tuning discussion step {i+1}",
            created_at=base_time + timedelta(minutes=2+i)
        ))
    db_session.commit()

    # Search historical messages
    results = conversation_memory_service.search_history(
        db_session,
        user_id=user["id"],
        query="What port did I configure for PostgreSQL?",
        current_chat_id=chat.id,
        scope="current"
    )
    assert len(results) > 0
    contents = [r["content"] for r in results]
    assert any("5434" in c for c in contents)


# ==============================================================================
# TEST 7: Semantic search of older messages through vector similarity
# ==============================================================================
def test_7_semantic_search_older_messages(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Semantic Memory Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(hours=4)
    med_text = "The Convergent Mediation batch ingestion cadence is set to fifteen seconds."
    
    db_session.add(Message(
        chat_id=chat.id,
        role="user",
        content=med_text,
        embedding=conversation_memory_service.embed_message_content(med_text),
        created_at=base_time
    ))
    db_session.commit()

    results = conversation_memory_service.search_history(
        db_session,
        user_id=user["id"],
        query="What interval did we decide for mediation batching?",
        current_chat_id=chat.id,
        scope="current"
    )
    assert len(results) > 0
    assert any("fifteen seconds" in r["content"] for r in results)


# ==============================================================================
# TEST 8: Distinguish historical recall question from standard technical SAP question
# ==============================================================================
def test_8_distinguish_historical_question_from_technical_sap():
    assert conversation_memory_service.classify_memory_intent("What was my first question in this chat?") == MemoryIntent.FIRST_MESSAGE_LOOKUP
    assert conversation_memory_service.classify_memory_intent("What was my first question?") == MemoryIntent.FIRST_MESSAGE_LOOKUP
    assert conversation_memory_service.classify_memory_intent("What did I ask at the beginning?") == MemoryIntent.FIRST_MESSAGE_LOOKUP
    
    assert conversation_memory_service.classify_memory_intent("What did we discuss earlier?") == MemoryIntent.HISTORY_RECALL
    assert conversation_memory_service.classify_memory_intent("What port did I configure for PostgreSQL?") == MemoryIntent.HISTORY_RECALL
    assert conversation_memory_service.classify_memory_intent("What was the issue I reported previously?") == MemoryIntent.HISTORY_RECALL

    assert conversation_memory_service.classify_memory_intent("What did we discuss in my previous chat about database?") == MemoryIntent.CROSS_CONVERSATION_RECALL
    assert conversation_memory_service.classify_memory_intent("Find the earlier discussion in my other chat") == MemoryIntent.CROSS_CONVERSATION_RECALL

    assert conversation_memory_service.classify_memory_intent("Explain the 3-Way Match verification process in SAP MM") == MemoryIntent.TECHNICAL_RAG
    assert conversation_memory_service.classify_memory_intent("How does Convergent Charging rate consumption CDRs in SAP BRIM?") == MemoryIntent.TECHNICAL_RAG


# ==============================================================================
# TEST 9: Mixed question requiring both conversation history and SAP BRIM docs
# ==============================================================================
def test_9_mixed_intent_conversation_and_sap_docs(db_session, registered_users):
    intent = conversation_memory_service.classify_memory_intent(
        "Based on the PostgreSQL port we discussed earlier, how does SAP BRIM Convergent Mediation connect to it?"
    )
    assert intent == MemoryIntent.MIXED


# ==============================================================================
# TEST 10: Non-fabrication when requested historical info does not exist
# ==============================================================================
def test_10_no_fabrication_when_historical_info_not_found(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Empty Topic Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    results = conversation_memory_service.search_history(
        db_session,
        user_id=user["id"],
        query="What did I say about Cassandra database replication factor?",
        current_chat_id=chat.id,
        scope="current"
    )
    assert len(results) == 0, "Should return empty list for topic never discussed"


# ==============================================================================
# TEST 11: Security & Isolation - One user cannot retrieve another user's conversations
# ==============================================================================
def test_11_cross_user_memory_isolation(db_session, registered_users):
    user_a = registered_users["user_a"]
    user_b = registered_users["user_b"]

    chat_a = Chat(user_id=user_a["id"], title="Secret Chat User A")
    db_session.add(chat_a)
    db_session.commit()
    db_session.refresh(chat_a)

    secret_text = "CONFIDENTIAL_PROJECT_AURORA_ACCESS_KEY_SECRET"
    db_session.add(Message(
        chat_id=chat_a.id,
        role="user",
        content=secret_text,
        embedding=conversation_memory_service.embed_message_content(secret_text)
    ))
    db_session.commit()

    # User B queries their history
    results_b = conversation_memory_service.search_history(
        db_session,
        user_id=user_b["id"],
        query="CONFIDENTIAL_PROJECT_AURORA",
        scope="all"
    )
    assert len(results_b) == 0, "User B must NEVER retrieve User A's messages"


# ==============================================================================
# TEST 12: Foreign conversation ID rejected
# ==============================================================================
def test_12_foreign_conversation_id_rejected(registered_users):
    user_a = registered_users["user_a"]
    user_b = registered_users["user_b"]

    create_resp = client.post("/api/chats", json={"title": "User A Private Chat"}, headers=user_a["headers"])
    assert create_resp.status_code == 201
    chat_a_id = create_resp.json()["id"]

    # User B attempts to access or send message to User A's chat
    send_resp = client.post(
        f"/api/chats/{chat_a_id}/messages",
        json={"content": "Malicious attempt to probe chat"},
        headers=user_b["headers"]
    )
    assert send_resp.status_code == 404, "Access to another user's chat must return 404 Not Found"


# ==============================================================================
# TEST 13: Deleting a conversation handles its associated memory data correctly
# ==============================================================================
def test_13_deleting_conversation_cascades_memory(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Chat To Delete", summary="Old summary")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    msg = Message(
        chat_id=chat.id,
        role="user",
        content="Message to be wiped",
        embedding=conversation_memory_service.embed_message_content("Message to be wiped")
    )
    db_session.add(msg)
    db_session.commit()

    # Delete via API or DB
    del_resp = client.delete(f"/api/chats/{chat.id}", headers=user["headers"])
    assert del_resp.status_code in (200, 204)

    # Check messages and chat are completely gone
    remaining_msgs = db_session.query(Message).filter(Message.chat_id == chat.id).all()
    assert len(remaining_msgs) == 0
    remaining_chat = db_session.query(Chat).filter(Chat.id == chat.id).first()
    assert remaining_chat is None


# ==============================================================================
# TEST 14: Existing RAG citations and grounding validation continue to work
# ==============================================================================
def test_14_existing_rag_citations_continue_working(db_session, registered_users):
    user = registered_users["user_a"]
    user_obj = db_session.query(User).filter(User.id == user["id"]).first()
    from offline_rag import RAG_QUESTION, offline_rag

    # Stub evidence and generation so this contract test does not rely on the external test DB corpus.
    with offline_rag():
        result = rag_service.process_query(db_session, RAG_QUESTION, user=user_obj)
    assert result["source_type"] == "knowledge_base"
    assert result["grounding_score"] > 0.0
    assert len(result["citations"]) > 0


# ==============================================================================
# TEST 15: Graceful operation when no historical messages or embeddings exist
# ==============================================================================
def test_15_graceful_operation_empty_history(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Fresh Brand New Chat")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    user_obj = db_session.query(User).filter(User.id == user["id"]).first()
    
    # Query with empty history
    result = rag_service.process_query(
        db_session,
        "What is Convergent Invoicing in SAP BRIM?",
        chat_history=[],
        user=user_obj,
        chat_id=chat.id
    )
    # Simple conceptual question routes to direct_llm via QueryRouter, bypassing retrieval
    assert result["source_type"] in ("direct_llm", "knowledge_base", "insufficient")
    assert result["answer"]


def test_16_summary_covers_messages_that_leave_recent_window_and_is_idempotent(db_session, registered_users):
    """Older messages are summarized in order once; recent 20 stay out of summary."""
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Summary watermark regression")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    base_time = datetime.now(timezone.utc) - timedelta(hours=1)
    messages = [
        Message(
            chat_id=chat.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Historical technical detail marker-{i+1}",
            created_at=base_time + timedelta(minutes=i),
        )
        for i in range(24)
    ]
    db_session.add_all(messages)
    db_session.commit()

    conversation_memory_service.update_rolling_summary(db_session, chat.id)
    db_session.refresh(chat)
    first_summary = chat.summary
    assert "marker-1" in first_summary
    assert "marker-4" in first_summary
    assert "marker-5" not in first_summary
    assert chat.summary_through_message_id == messages[3].id
    assert len(conversation_memory_service.get_recent_messages(db_session, chat.id, limit=20)) == 20

    # A repeated call does not duplicate entries.
    conversation_memory_service.update_rolling_summary(db_session, chat.id)
    db_session.refresh(chat)
    assert chat.summary == first_summary

    later = [
        Message(
            chat_id=chat.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"New technical detail marker-{i+1}",
            created_at=base_time + timedelta(minutes=i),
        )
        for i in range(24, 26)
    ]
    db_session.add_all(later)
    db_session.commit()
    conversation_memory_service.update_rolling_summary(db_session, chat.id)
    db_session.refresh(chat)
    assert "marker-5" in chat.summary
    assert "marker-6" in chat.summary
    assert chat.summary.count("marker-1") == 1
    assert chat.summary_through_message_id == messages[5].id


def test_17_summary_failure_does_not_advance_watermark(db_session, registered_users, monkeypatch):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Summary rollback")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    base_time = datetime.now(timezone.utc) - timedelta(minutes=40)
    db_session.add_all([
        Message(chat_id=chat.id, role="user", content=f"Rollback detail {i}", created_at=base_time + timedelta(minutes=i))
        for i in range(22)
    ])
    db_session.commit()

    real_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("simulated commit failure")))
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        conversation_memory_service.update_rolling_summary(db_session, chat.id)
    db_session.rollback()
    monkeypatch.setattr(db_session, "commit", real_commit)

    db_session.refresh(chat)
    assert chat.summary is None
    assert chat.summary_through_created_at is None
    assert chat.summary_through_message_id is None


def test_18_lexical_recall_survives_missing_or_failed_embeddings(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="No embeddings")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    msg = Message(chat_id=chat.id, role="user", content="Our agreed PostgreSQL port is 55439.")
    db_session.add(msg)
    db_session.commit()

    with patch("backend.app.services.conversation_memory_service.embedding_service.embed_text", side_effect=RuntimeError("model unavailable")):
        assert conversation_memory_service.embed_message_content("some content") is None
        results = conversation_memory_service.search_history(
            db_session,
            user_id=user["id"],
            query="What PostgreSQL port did we agree?",
            current_chat_id=chat.id,
            scope="current",
        )
    assert results
    assert results[0]["message_id"] == msg.id


def test_19_concurrent_summary_updates_do_not_duplicate_excerpts(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Concurrent summary updates")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    base_time = datetime.now(timezone.utc) - timedelta(hours=2)
    messages = [
        Message(chat_id=chat.id, role="user" if i % 2 == 0 else "assistant",
                content=f"Concurrent marker-{i+1}", created_at=base_time + timedelta(minutes=i))
        for i in range(24)
    ]
    db_session.add_all(messages)
    db_session.commit()
    chat_id = chat.id

    def update_summary():
        with SessionLocal() as local_db:
            conversation_memory_service.update_rolling_summary(local_db, chat_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: update_summary(), range(2)))

    db_session.expire_all()
    refreshed = db_session.query(Chat).filter(Chat.id == chat.id).one()
    assert refreshed.summary.count("marker-1") == 1
    assert refreshed.summary.count("marker-4") == 1
    assert refreshed.summary_through_message_id == messages[3].id


def test_20_streaming_and_non_streaming_history_recall_match(db_session, registered_users):
    user = registered_users["user_a"]
    chat = Chat(user_id=user["id"], title="Memory stream parity")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    db_session.add(Message(chat_id=chat.id, role="user", content="What was the original incident?"))
    db_session.commit()
    history = conversation_memory_service.get_recent_messages(db_session, chat.id)
    user_obj = db_session.query(User).filter(User.id == user["id"]).one()

    synchronous = rag_service.process_query(
        db_session, "What was my first question in this chat?", chat_history=history,
        user=user_obj, chat_id=chat.id,
    )
    events = list(rag_service.stream_query(
        db_session, "What was my first question in this chat?", chat_history=history,
        user=user_obj, chat_id=chat.id,
    ))
    streamed = events[-1]
    assert synchronous["answer"] == streamed["answer"]
    assert synchronous["source_type"] == streamed["source_type"] == "conversation_memory"
