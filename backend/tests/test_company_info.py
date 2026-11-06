"""Questions about Clyptus itself are answered with the fixed company profile, not the SAP-only refusal."""
import pytest

from backend.app.api import messages
from backend.app.services.company_info import COMPANY_ANSWER, is_company_question
from backend.app.services.sap_classifier import NON_SAP_REFUSAL_RESPONSE


@pytest.mark.parametrize("text", [
    "What is Clyptus?", "what is clyptus.ai", "Tell me about the Clyptus company", "Who is Clyptus Technologies?",
    "about clyptus", "What does Clyptus do?", "who built you?", "Who created this?", "which company made you",
])
def test_company_questions_are_detected(text):
    assert is_company_question(text)


@pytest.mark.parametrize("text", [
    "", "What is convergent charging?", "recipe for pizza", "Who is Elon Musk?", "who are you",
    "How do I configure FI-CA dunning?", "What is the weather today?",
])
def test_other_questions_are_not_company_questions(text):
    assert not is_company_question(text)


def test_answer_is_taken_from_the_about_page_and_makes_no_invented_claims():
    assert "Clyptus Technologies" in COMPANY_ANSWER and "Clyptus.AI" in COMPANY_ANSWER and "SAP BRIM" in COMPANY_ANSWER
    for invented in ("founded in", "headquarter", "employees", "$"):
        assert invented not in COMPANY_ANSWER


def test_sprint_answers_company_question_instead_of_refusing():
    result = messages._sprint_result("What is Clyptus?", [], None)
    assert result["answer"] == COMPANY_ANSWER
    assert result["source_type"] == "conversational"


def test_sprint_still_refuses_unrelated_questions():
    result = messages._sprint_result("Give me a pizza recipe", [], None)
    assert result["answer"] == NON_SAP_REFUSAL_RESPONSE and result["source_type"] == "refusal"


def test_an_attachment_turn_is_never_treated_as_a_company_question():
    assert messages._sprint_route("What is Clyptus?", [], [{"text": "unrelated"}], {}) != "company"


def test_scholar_answers_company_question_without_retrieval_or_model_calls():
    from unittest.mock import MagicMock

    from backend.app.services.rag_service import rag_service

    db = MagicMock()
    result = rag_service.process_query(db, "What is Clyptus?")
    assert result["answer"] == COMPANY_ANSWER
    assert result["source_type"] == "conversational"
    assert result["citations"] == [] and result["external_search_used"] is False
    db.execute.assert_not_called()


def test_scholar_still_refuses_unrelated_questions():
    from unittest.mock import MagicMock

    from backend.app.services.rag_service import rag_service

    result = rag_service.process_query(MagicMock(), "Give me a pizza recipe")
    assert result["source_type"] == "refusal"
