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
        assert "I can only help with SAP and SAP-related topics." in msg

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
