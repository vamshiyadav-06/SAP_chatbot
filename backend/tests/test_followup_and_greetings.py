import pytest
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.query_rewriter import query_rewriter

def test_sentimental_and_greetings_rejected():
    greetings = [
        "hii",
        "hi",
        "hello",
        "hey",
        "how are you",
        "who are you",
        "what's your name",
        "good morning",
        "thank you",
        "tell me a joke",
        "are you human",
    ]
    for g in greetings:
        is_sap, msg = sap_classifier.classify(g)
        assert not is_sap, f"Greeting '{g}' should be rejected"
        assert "I can only assist with SAP and SAP-related topics." in msg

def test_greetings_not_treated_as_followup_even_with_history():
    history = [
        {"role": "user", "content": "What is SAP Convergent Charging?"},
        {"role": "assistant", "content": "## SAP Convergent Charging Overview\nSAP CC is a rating and charging engine."}
    ]
    greetings = ["hii", "hello", "how are you", "thanks"]
    for g in greetings:
        cand, reason = query_rewriter.is_follow_up_candidate(g, history)
        assert not cand, f"'{g}' should NOT be treated as a follow-up candidate, got {reason}"

def test_genuine_followup_accepted_with_history():
    history = [
        {"role": "user", "content": "What is SAP Convergent Charging?"},
        {"role": "assistant", "content": "## SAP Convergent Charging Overview\nSAP CC is a rating and charging engine."}
    ]
    followups = [
        "can you explain in detail?",
        "what are its key components?",
        "how is it configured?",
        "what are the prerequisites?",
        "what happens after rating?",
    ]
    for q in followups:
        cand, reason = query_rewriter.is_follow_up_candidate(q, history)
        assert cand, f"'{q}' should be identified as a follow-up candidate"
        resolution = query_rewriter.resolve_query(q, history)
        resolved = resolution["resolved_query"]
        is_sap, _ = sap_classifier.classify(resolved)
        assert is_sap, f"Resolved query '{resolved}' should be verified as SAP-related"


def test_memory_followups_resolve_against_earlier_fica_context(monkeypatch):
    from backend.app.services.query_rewriter import query_rewriter

    fica_history = [
        {"role": "user", "content": "What is FI-CA?"},
        {"role": "assistant", "content": "FI-CA is Contract Accounts Receivable and Payable."},
    ]
    approach_history = [
        {"role": "user", "content": "We previously used a manual reconciliation approach."},
        {"role": "assistant", "content": "That approach required manual matching of records."},
    ]
    cases = [
        ("Explain it in more detail.", fica_history, "FI-CA"),
        ("What are its main components?", fica_history, "FI-CA"),
        ("Compare this with the previous approach.", approach_history, "previous approach discussed earlier"),
    ]
    monkeypatch.setattr(query_rewriter, "client", None)

    for query, history, expected in cases:
        resolution = query_rewriter.resolve_query(query, chat_history=history)
        assert resolution["is_follow_up"] is True
        assert expected.lower() in resolution["resolved_query"].lower()


def test_unrelated_questions_rejected_even_with_history():
    history = [
        {"role": "user", "content": "What is SAP Convergent Invoicing?"},
        {"role": "assistant", "content": "SAP CI handles billing and invoicing."}
    ]
    unrelated = [
        "what is python?",
        "who is elon musk?",
        "how is the weather in new york?",
        "tell me a recipe for chocolate cake"
    ]
    for q in unrelated:
        cand, _ = query_rewriter.is_follow_up_candidate(q, history)
        assert not cand, f"'{q}' should not be a follow-up"
        is_sap, _ = sap_classifier.classify(q)
        assert not is_sap, f"'{q}' should be rejected by classifier"


def test_conversational_and_sentimental_detected():
    conversational_queries = [
        "what are you doing ?",
        "what are you doing",
        "hi",
        "hii",
        "hello",
        "hey there",
        "who are you?",
        "what can you do?",
        "how can you help me?",
        "how are you?",
    ]
    for q in conversational_queries:
        is_conv = sap_classifier.is_conversational_or_greeting(q)
        assert is_conv is True, f"Query '{q}' should be detected as conversational"


def test_conversational_rag_service_flow():
    from backend.app.database import SessionLocal, init_db
    from backend.app.services.rag_service import rag_service

    init_db()
    db = SessionLocal()
    try:
        res = rag_service.process_query(db, "what are you doing ?")
        assert res["source_type"] == "conversational"
        # Small talk skips retrieval, so it is never labelled verified (AUDIT_REPORT F-04).
        assert res["verification_status"] == "unverified" and res["grounding_score"] is None
        assert "SAP" in res["answer"]
        assert len(res["follow_up_questions"]) == 3
        for fq in res["follow_up_questions"]:
            assert fq.endswith("?")
    finally:
        db.close()

