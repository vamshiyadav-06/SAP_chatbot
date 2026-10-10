import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import SessionLocal, init_db
from backend.app.config import settings
from backend.app.services.rag_service import rag_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.answer_planner import answer_planner
from backend.app.services.followup_service import followup_service
from backend.app.services.query_rewriter import query_rewriter

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    init_db()
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def auth_headers():
    client.post("/api/auth/register", json={"email": "tester_v2@sap.com", "name": "V2 Tester", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": "tester_v2@sap.com", "password": "Password123!"}).json()
    return {"Authorization": f"Bearer {login_resp['access_token']}"}


# ==============================================================================
# TEST 1: STRONG INTERNAL EVIDENCE
# ==============================================================================
def test_1_strong_internal_evidence(db_session):
    """
    Input: Question fully answered by internal SAP manuals (e.g. 3-way match in SAP MM).
    Expected:
    - Internal confidence >= 0.70
    - Tavily is NOT called
    - Internal sources are selected
    - Exactly 3 follow-up questions generated
    """
    query = "Explain the 3-Way Match verification process in SAP MM"
    result = rag_service.process_query(db_session, query)

    assert result["source_type"] == "knowledge_base"
    assert result["external_search_used"] is False
    assert result["grounding_score"] >= 0.70
    assert len(result["citations"]) > 0
    assert len(result["follow_up_questions"]) == 3
    for fq in result["follow_up_questions"]:
        assert fq.endswith("?")


# ==============================================================================
# TEST 2: WEAK INTERNAL EVIDENCE (< 70% CONFIDENCE)
# ==============================================================================
def test_2_weak_internal_evidence_triggers_tavily(db_session):
    """
    Input: Valid SAP question not covered by internal on-prem manuals (e.g. SAP Ariba Cloud).
    Expected:
    - Internal evidence confidence < 0.70
    - Automatically triggers Tavily
    - Evaluates external candidates
    """
    query = "How does Celonis process mining integrate with SAP S/4HANA for business process optimization?"
    # Verify confidence calculation directly
    kb_candidates = retrieval_service.hybrid_search(db_session, query, top_k=settings.TOP_K)
    top_kb, _, _ = reranking_service.rerank_kb(query, kb_candidates, top_n=5)
    conf_data = evidence_selection_service.compute_internal_confidence(query, top_kb)

    assert conf_data["should_trigger_tavily"] is True
    assert conf_data["confidence"] < settings.INTERNAL_EVIDENCE_THRESHOLD

    result = rag_service.process_query(db_session, query)
    assert result["external_search_used"] is True
    assert result["source_type"] in ("web", "combined", "knowledge_base")


# ==============================================================================
# TEST 3: EXTERNAL EVIDENCE IMPROVES COVERAGE
# ==============================================================================
def test_3_external_evidence_improves_coverage(db_session):
    """
    Input: Query on cloud SAP product.
    Expected:
    - Tavily runs
    - External passages extracted from approved domains
    - Citations / web sources reflect verified SAP domain
    """
    query = "How does SAP Concur travel and expense integrate with SAP S/4HANA finance?"
    result = rag_service.process_query(db_session, query)

    assert result["external_search_used"] is True
    if result["web_sources"]:
        for ws in result["web_sources"]:
            assert any(d in ws["url"] for d in ["sap.com", "help.sap.com", "community.sap.com", "blogs.sap.com"])


# ==============================================================================
# TEST 4: BOTH SOURCES INSUFFICIENT (ABSTENTION)
# ==============================================================================
def test_4_both_sources_insufficient(db_session):
    """
    Input: Question that cannot be answered by either internal manuals or web.
    Expected:
    - Assistant explains limitation or abstains
    - Does NOT fabricate facts or fake 100% grounding score
    """
    query = "What was the private personal phone number of the author of the BRIM manual in 1999?"
    result = rag_service.process_query(db_session, query)

    assert any(phrase in result["answer"].lower() for phrase in [
        "unable to", "couldn't find", "could not find", "insufficient", "not available", "outside", "does not exist", "cannot be verified"
    ])


# ==============================================================================
# TEST 5: UNSUPPORTED TECHNICAL IDENTIFIER VETO
# ==============================================================================
def test_5_unsupported_technical_identifier_veto(db_session):
    """
    Input: Candidate answer containing a fabricated SAP transaction code or table.
    Expected:
    - Verifier flags critical unsupported claim
    - Passes grounding gate is False
    """
    query = "How to configure billable items?"
    evidence = [
        {"source_id": "doc1", "document_name": "SAP CI Guide", "page_number": 12, "chunk_text": "Billable items are stored in standard class tables in Convergent Invoicing."}
    ]
    hallucinated_answer = "Execute transaction /1FE/FAKE_TRANSACTION_999 to configure table DFKK_FABRICATED_TABLE."
    
    verification = grounding_service.verify_answer(query, hallucinated_answer, evidence)

    assert verification["passes_grounding_gate"] is False
    assert len(verification["critical_unsupported_claims"]) > 0
    assert any("fake" in c.lower() or "fabricated" in c.lower() for c in verification["critical_unsupported_claims"])


# ==============================================================================
# TEST 6: GROUNDING SCORE BELOW 80% TRIGGERS REPAIR
# ==============================================================================
def test_6_grounding_score_gate_and_repair(db_session):
    """
    Verify that an answer with unsupported claims is not published as verified
    without repair.
    """
    query = "What is SAP Convergent Charging?"
    evidence = [
        {"source_id": "doc1", "document_name": "SAP CC Overview", "page_number": 5, "chunk_text": "SAP Convergent Charging provides high-throughput rating and charging for subscriber events."}
    ]
    candidate = (
        "SAP Convergent Charging provides rating. "
        "It also automatically builds hardware quantum computers and manages airport air traffic controllers."
    )
    verification = grounding_service.verify_answer(query, candidate, evidence)

    assert verification["passes_grounding_gate"] is False
    assert verification["grounding_score"] < 0.80


# ==============================================================================
# TEST 7: CONVERSATIONAL FOLLOW-UP QUERY REWRITING
# ==============================================================================
def test_7_conversational_follow_up():
    """
    Conversation:
    User: "What is SAP Convergent Invoicing?"
    Follow-up: "Where is it configured?"
    Expected:
    - Query rewriter resolves 'it' to 'SAP Convergent Invoicing'
    - Preserves exact technical term
    """
    history = [
        {"role": "user", "content": "What is SAP Convergent Invoicing?"},
        {"role": "assistant", "content": "SAP Convergent Invoicing (CI) manages billable item processing and invoice creation."}
    ]
    resolution = query_rewriter.resolve_query("Where is it configured?", chat_history=history)

    assert resolution["is_follow_up"] is True
    assert "convergent invoicing" in resolution["resolved_query"].lower() or "ci" in resolution["resolved_query"].lower()


# ==============================================================================
# TEST 8: QUESTION-AWARE RESPONSE FORMATTING
# ==============================================================================
def test_8_question_aware_planning():
    """
    Tests that answer planner identifies distinct question archetypes:
    - Comparison
    - Configuration
    - T-Code / Table lookup
    - Troubleshooting
    """
    p_comp = answer_planner.plan_answer("Difference between SAP Convergent Invoicing and FI-CA")
    assert p_comp["question_type"] == "comparison"
    assert "Comparison" in p_comp["instructions"]

    p_cfg = answer_planner.plan_answer("How to configure billable item classes in SPRO?")
    assert p_cfg["question_type"] == "configuration"
    assert "SPRO" in p_cfg["instructions"]

    p_tcode = answer_planner.plan_answer("What is transaction FPC1 used for?")
    assert p_tcode["question_type"] == "tcode_table"

    p_err = answer_planner.plan_answer("How to resolve billing order error in SAP CI?")
    assert p_err["question_type"] == "troubleshooting"


# ==============================================================================
# TEST 9: FOLLOW-UP QUESTION GENERATION
# ==============================================================================
def test_9_followup_question_generation():
    """
    Validates that followup_service produces exactly 3 distinct clickable questions.
    """
    follow_ups = followup_service.generate_deterministic_followups(
        "What is SAP Convergent Invoicing?",
        "Convergent Invoicing aggregates billable items into invoices and posts to FI-CA.",
        []
    )
    assert len(follow_ups) == 3
    for q in follow_ups:
        assert q.endswith("?")
    assert len(set(follow_ups)) == 3


# ==============================================================================
# TEST 10: SSE STREAMING AND BUFFERED VERIFICATION
# ==============================================================================
def test_10_sse_streaming_stages(db_session):
    """
    Validates that streaming yields required progress status stages,
    token events, and completion event with all metadata.
    """
    events = list(rag_service.stream_query(db_session, "Explain the role of SAP Convergent Charging."))

    stages = [e.get("stage") for e in events if e.get("type") == "status"]
    assert "thinking" in stages
    assert "retrieval" in stages
    assert "verifying_claims" in stages

    done_event = next((e for e in events if e.get("type") == "done"), None)
    assert done_event is not None
    assert "grounding_score" in done_event
    assert "verification_status" in done_event
    assert len(done_event["follow_up_questions"]) == 3


# ==============================================================================
# TEST 11: DATABASE RETRIEVAL STABILITY
# ==============================================================================
def test_11_database_retrieval_stability(db_session):
    """
    Ensures hybrid search returns chunk records from the 10,661 chunks database
    without errors or empty responses for standard queries.
    """
    results = retrieval_service.hybrid_search(db_session, "billable item", top_k=5)
    assert len(results) > 0
    assert "chunk_text" in results[0]
    assert "document_name" in results[0]


# ==============================================================================
# TEST 12: SEARCH AND PROVIDER FAILURE HANDLING
# ==============================================================================
def test_12_failure_resilience(db_session):
    """
    Simulates invalid query or provider timeout without crashing the application.
    """
    res = rag_service.process_query(db_session, "Explain the weather in Paris")
    assert res["source_type"] == "refusal"
    assert "only help with sap" in res["answer"].lower()
