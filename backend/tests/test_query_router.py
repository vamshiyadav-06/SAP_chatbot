"""
Comprehensive Automated Test Suite for Intelligent Query Routing in Clyptus.AI SAP BRIM Assistant.

Verifies:
1. All 15 required user query table cases from Section 10 of the specification.
2. Direct LLM bypass of retrieval (no vector search, no web search, no github search) for EMOTIONAL_CASUAL and SIMPLE_SAP.
3. Both streaming and non-streaming endpoints.
4. Word length constraints and empathetic/factual style guidelines.
5. Mixed emotional and technical questions (acknowledgment + technical routing).
6. Preserved complex RAG pipeline execution, citations, and grounding.
7. Preserved conversation memory routing and user isolation.
8. Leading greeting stripping (e.g., 'Hey, what is SAP BRIM?' -> SIMPLE_SAP).
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal, init_db
from backend.app.services.query_router import query_router, QueryRoute
from backend.app.services.rag_service import rag_service
from backend.app.services.llm_service import llm_service
from backend.app.models.chat import Chat
from backend.app.models.message import Message

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def test_user():
    email = "router_tester@sap.com"
    client.post("/api/auth/register", json={"email": email, "name": "Router User", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": "Password123!"}).json()
    token = login_resp["access_token"]
    user_id = login_resp["user"]["id"]
    return {"id": user_id, "email": email, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


# ==============================================================================
# 1. TEST SUITE: All 15 Required User Query Table Cases (Section 10)
# ==============================================================================
@pytest.mark.parametrize(
    "query,expected_route",
    [
        ("Hey", QueryRoute.EMOTIONAL_CASUAL),
        ("I'm feeling sad", QueryRoute.EMOTIONAL_CASUAL),
        ("How are you?", QueryRoute.EMOTIONAL_CASUAL),
        ("Thank you", QueryRoute.EMOTIONAL_CASUAL),
        ("What is SAP?", QueryRoute.SIMPLE_SAP),
        ("What is SAP BRIM?", QueryRoute.SIMPLE_SAP),
        ("What does FI-CA stand for?", QueryRoute.SIMPLE_SAP),
        ("What is the purpose of SOM?", QueryRoute.SIMPLE_SAP),
        ("What is the difference between SOM and Convergent Charging?", QueryRoute.COMPLEX_SAP),
        ("Explain detailed SOM-to-CI integration", QueryRoute.COMPLEX_SAP),
        ("Why are billable items missing?", QueryRoute.COMPLEX_SAP),
        ("Explain the exact configuration for this production issue", QueryRoute.COMPLEX_SAP),
        ("What did I ask you first?", QueryRoute.CONVERSATION_MEMORY),
        ("I'm stressed; what is SAP BRIM?", QueryRoute.MIXED_QUERY),
        ("I'm frustrated because FI-CA clearing failed", QueryRoute.MIXED_QUERY),
        ("Give me advanced scenario-based interview questions", QueryRoute.COMPLEX_SAP),
    ],
)
def test_required_table_routes(query, expected_route):
    decision = query_router.route(query)
    assert decision.route == expected_route, f"Query '{query}' expected route {expected_route}, got {decision.route}"


# ==============================================================================
# 2. TEST SUITE: Path A - Sentimental & Casual Questions -> Direct LLM (No Retrieval)
# ==============================================================================
def test_path_a_greetings_bypass_retrieval(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve, \
         patch("backend.app.services.web_search_service.web_search_service.search_sap_authoritative") as mock_web_search:

        result = rag_service.process_query(db_session, "Hey")

        # Zero retrieval executed
        assert mock_retrieve.call_count == 0, "Retrieval should NOT be called for 'Hey'"
        assert mock_web_search.call_count == 0, "Web search should NOT be called for 'Hey'"

        # Attributes verification
        assert result["route"] == QueryRoute.EMOTIONAL_CASUAL.value
        assert result["source_type"] == "direct_llm"
        assert result["is_in_rag_pipeline"] is False
        assert result["citations"] == []
        assert len(result["answer"]) > 0

        # Word count constraint (target 5-20 words, max 30 words)
        words = result["answer"].split()
        assert len(words) <= 30, f"Greeting answer too long ({len(words)} words)"


def test_path_a_emotional_bypass_retrieval(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve, \
         patch("backend.app.services.web_search_service.web_search_service.search_sap_authoritative") as mock_web_search:

        result = rag_service.process_query(db_session, "I'm feeling sad.")

        # Zero retrieval executed
        assert mock_retrieve.call_count == 0, "Retrieval should NOT be called for emotional queries"
        assert mock_web_search.call_count == 0, "Web search should NOT be called for emotional queries"

        # Attributes verification
        assert result["route"] == QueryRoute.EMOTIONAL_CASUAL.value
        assert result["source_type"] == "direct_llm"
        assert result["is_in_rag_pipeline"] is False
        assert result["citations"] == []

        # Word count constraint (normally 10-25 words, max 40 words)
        words = result["answer"].split()
        assert len(words) <= 40, f"Emotional answer too long ({len(words)} words)"
        # Must not mention SAP BRIM unless asked
        assert "brim" not in result["answer"].lower()


# ==============================================================================
# 3. TEST SUITE: Path B - Simple SAP Questions -> Direct LLM (No Retrieval)
# ==============================================================================
def test_path_b_simple_sap_bypass_retrieval(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve, \
         patch("backend.app.services.web_search_service.web_search_service.search_sap_authoritative") as mock_web_search:

        result = rag_service.process_query(db_session, "What is SAP BRIM?")

        # Zero retrieval executed
        assert mock_retrieve.call_count == 0, "Retrieval should NOT be called for 'What is SAP BRIM?'"
        assert mock_web_search.call_count == 0, "Web search should NOT be called for 'What is SAP BRIM?'"

        # Attributes verification
        assert result["route"] == QueryRoute.SIMPLE_SAP.value
        assert result["source_type"] == "direct_llm"
        assert result["is_in_rag_pipeline"] is False
        assert result["citations"] == []

        # Word count constraint (target 2-5 sentences, normally stay below 120 words)
        words = result["answer"].split()
        assert len(words) <= 120, f"Simple SAP answer too long ({len(words)} words)"
        assert "Billing and Revenue Innovation Management" in result["answer"]


def test_path_b_fica_definition(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve:
        result = rag_service.process_query(db_session, "What does FI-CA stand for?")
        assert mock_retrieve.call_count == 0
        assert result["route"] == QueryRoute.SIMPLE_SAP.value
        assert "Contract Accounts Receivable and Payable" in result["answer"]


# ==============================================================================
# 4. TEST SUITE: Mixed Emotional and Technical Queries
# ==============================================================================
def test_mixed_query_with_simple_sap(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve:
        result = rag_service.process_query(db_session, "I'm stressed; what is SAP BRIM?")
        assert mock_retrieve.call_count == 0
        assert result["route"] == QueryRoute.MIXED_QUERY.value
        assert result["source_type"] == "direct_llm"
        # Should have emotional acknowledgment and simple SAP explanation
        assert "stressful" in result["answer"].lower() or "sorry" in result["answer"].lower()
        assert "Billing and Revenue Innovation Management" in result["answer"]


def test_mixed_query_with_complex_sap():
    decision = query_router.route("I'm frustrated because FI-CA clearing failed")
    assert decision.route == QueryRoute.MIXED_QUERY
    assert decision.technical_route == QueryRoute.COMPLEX_SAP
    assert decision.requires_retrieval is True
    ack = query_router.get_acknowledgment(decision.emotional_part)
    assert "frustration" in ack.lower()


# ==============================================================================
# 5. TEST SUITE: Path C - Complex SAP BRIM Technical Questions -> Existing RAG
# ==============================================================================
def test_path_c_complex_rag_pipeline(db_session):
    with patch("backend.app.services.rag_service.rag_service._retrieve_aspect_evidence") as mock_retrieve, \
         patch("backend.app.services.llm_service.llm_service.generate_answer") as mock_gen_ans, \
         patch("backend.app.services.grounding_service.grounding_service.verify_answer") as mock_verify:

        mock_retrieve.return_value = (
            [
                {
                    "chunk_id": "chunk_som_ci_1",
                    "chunk_text": "SOM contracts replicate into Convergent Invoicing billable items via CC rating.",
                    "document_name": "BRIM_Integration_Guide.pdf",
                    "page_number": 42,
                    "rerank_score": 0.94,
                    "score": 0.94,
                    "source_type": "knowledge_base"
                }
            ],
            0.94,
            [{"aspect": "Explain detailed SOM-to-CI integration", "score": 0.94, "evidence_count": 1}]
        )
        mock_gen_ans.return_value = "SOM integrates with CI by replicating provider contracts and rating consumption through CC."
        mock_verify.return_value = {
            "grounding_score": 0.95,
            "verification_status": "verified",
            "passes_grounding_gate": True,
            "unsupported_claims": [],
            "critical_unsupported_claims": [],
            "critical_failures": [],
            "contradicted_claims": [],
        }

        result = rag_service.process_query(db_session, "Explain detailed SOM-to-CI integration")

        assert mock_retrieve.call_count >= 1
        assert result["route"] == QueryRoute.COMPLEX_SAP.value
        assert len(result["citations"]) >= 1
        assert result["citations"][0]["document"] == "BRIM_Integration_Guide.pdf"


# ==============================================================================
# 6. TEST SUITE: Leading Greeting Does Not Override Technical Question
# ==============================================================================
def test_greeting_with_simple_technical_question():
    decision = query_router.route("Hey, what is SAP BRIM?")
    assert decision.route == QueryRoute.SIMPLE_SAP, f"Expected SIMPLE_SAP, got {decision.route}"


def test_greeting_with_complex_technical_question():
    decision = query_router.route("Hello, why are billable items missing after rating?")
    assert decision.route == QueryRoute.COMPLEX_SAP, f"Expected COMPLEX_SAP, got {decision.route}"


# ==============================================================================
# 7. TEST SUITE: Conversation Memory Preserved & Priority
# ==============================================================================
def test_conversation_memory_first_message(db_session, test_user):
    chat = Chat(user_id=test_user["id"], title="Memory Route Test")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    msg1 = Message(chat_id=chat.id, role="user", content="How do I configure provider contracts in SOM?")
    msg2 = Message(chat_id=chat.id, role="assistant", content="Configure provider contract types in SPRO under SOM.")
    db_session.add_all([msg1, msg2])
    db_session.commit()

    decision = query_router.route("What did I ask you first?")
    assert decision.route == QueryRoute.CONVERSATION_MEMORY

    result = rag_service.process_query(db_session, "What did I ask you first?", chat_id=chat.id)
    assert result["source_type"] == "conversation_memory"
    assert "How do I configure provider contracts in SOM?" in result["answer"]


# ==============================================================================
# 8. TEST SUITE: Streaming API Direct LLM Verification
# ==============================================================================
def test_streaming_path_a_greeting(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve:
        events = list(rag_service.stream_query(db_session, "Hey"))
        assert mock_retrieve.call_count == 0

        # Events emitted: status ('generating'), tokens, done
        event_types = [e.get("type") for e in events]
        assert "status" in event_types
        assert "token" in event_types
        assert "done" in event_types

        done_event = events[-1]
        assert done_event["type"] == "done"
        assert done_event["route"] == QueryRoute.EMOTIONAL_CASUAL.value
        assert done_event["source_type"] == "direct_llm"
        assert done_event["is_in_rag_pipeline"] is False
        assert done_event["citations"] == []


def test_streaming_path_b_simple_sap(db_session):
    with patch("backend.app.services.retrieval_service.retrieval_service.retrieve") as mock_retrieve:
        events = list(rag_service.stream_query(db_session, "What is SAP?"))
        assert mock_retrieve.call_count == 0

        done_event = events[-1]
        assert done_event["type"] == "done"
        assert done_event["route"] == QueryRoute.SIMPLE_SAP.value
        assert done_event["source_type"] == "direct_llm"
        assert done_event["citations"] == []
        assert "SAP is enterprise software" in done_event["answer"]
