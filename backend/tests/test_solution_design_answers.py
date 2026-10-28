"""
Broad design / interview questions ("How would you design an end-to-end BRIM solution ... while handling
production failures") must retrieve evidence for every listed topic and for production operations, and
be laid out as a senior solution answer instead of a one-aspect architecture overview.
"""

from unittest.mock import MagicMock

import pytest

from backend.app.services import answer_style_router as router_module
from backend.app.services.answer_planner import TROUBLESHOOTING_PATTERN
from backend.app.services.answer_style_router import answer_style_router, is_solution_design_question
from backend.app.services.llm_service import EVIDENCE_AWARE_ANSWER_INSTRUCTIONS, llm_service
from backend.app.services.rag_service import MAX_SCENARIO_ASPECTS, OPERATIONS_ASPECTS, RAGService

DESIGN_QUESTION = (
    "must be 7+ years exp candidate\n"
    "How would you design and implement an end-to-end SAP BRIM solution covering SOM, subscription lifecycle "
    "management, SAP CC rating, CI billing and invoicing, FI-CA integration, and high-volume usage processing, "
    "while handling complex pricing, billing discrepancies, performance bottlenecks, and production failures "
    "for a large enterprise?"
)
KB = [{"source_type": "knowledge_base", "evidence_id": "E1", "document_name": "CI Guide", "page_number": 4,
       "chunk_text": "Billable items are grouped into billing documents by the billing process."}]


@pytest.fixture(autouse=True)
def _no_classifier(monkeypatch):
    router_module._classifier_cache.clear()
    monkeypatch.setattr(llm_service, "classify_answer_style", MagicMock(return_value=None))
    yield
    router_module._classifier_cache.clear()


def test_design_interview_question_gets_solution_design_layout():
    plan = answer_style_router.route(DESIGN_QUESTION, KB)
    assert plan.answer_type == "solution_design"
    assert plan.detail_level == "detailed" and plan.max_sections == 8 and plan.needs_steps

    prompt = llm_service._build_answer_prompt(DESIGN_QUESTION, KB, "knowledge_base", answer_plan=plan)
    assert "troubleshooting playbook" in prompt
    assert "duplicate usage events" in prompt and "FI-CA posting errors" in prompt
    assert "monitoring and alerting, error reprocessing, performance tuning and recovery" in prompt
    assert "write a model answer in the first person" in prompt
    assert "never invent client names, project figures, volumes or outcomes" in prompt
    # Evidence and citation rules still apply.
    assert "Every factual SAP statement must be supported by a passage above" in prompt


def test_design_question_retrieves_every_topic_and_production_operations():
    aspects = RAGService.split_question_aspects(DESIGN_QUESTION)
    assert len(aspects) <= MAX_SCENARIO_ASPECTS
    joined = "\n".join(aspects)
    for topic in ["SOM", "SAP CC rating", "CI billing and invoicing", "FI-CA integration",
                  "high-volume usage processing", "complex pricing", "billing discrepancies",
                  "performance bottlenecks", "production failures"]:
        assert topic in joined, topic
    assert all(a in aspects for a in OPERATIONS_ASPECTS)
    assert not any(a.startswith("SAP BRIM while") for a in aspects)


def test_design_question_without_operations_gets_no_operations_aspects():
    question = "How would you design an end-to-end SAP BRIM solution covering SOM, SAP CC rating and CI billing?"
    aspects = RAGService.split_question_aspects(question)
    assert len(aspects) > 1
    assert not any(a in aspects for a in OPERATIONS_ASPECTS)


@pytest.mark.parametrize("question, expected", [
    ("How does Convergent Invoicing process billable items?", "technical_explanation"),
    ("Billing run fails with error message FKKBIX 012, how do I fix it?", "troubleshooting"),
    ("How would you fix billing run failures?", "troubleshooting"),
    ("How do I create a billable item class?", "step_by_step"),
    ("How would you handle duplicate usage events?", "solution_design"),
])
def test_ordinary_questions_keep_their_layout(question, expected):
    assert answer_style_router.route(question, KB).answer_type == expected


@pytest.mark.parametrize("question", [
    "How does Convergent Invoicing process billable items?",
    "What is the difference between Convergent Invoicing and FI-CA?",
])
def test_ordinary_questions_are_not_split(question):
    assert RAGService.split_question_aspects(question) == [question]
    assert not is_solution_design_question(question)


def test_plural_failures_count_as_troubleshooting():
    assert TROUBLESHOOTING_PATTERN.search("billing run failures")


def test_interleave_puts_one_passage_per_aspect_first():
    aspects = [{"aspect": a, "score": 0.8, "evidence_count": 1} for a in ("A", "B", "C")]
    selected = [{"question_aspect": "A", "chunk_text": "a1"}, {"question_aspect": "A", "chunk_text": "a2"}]
    internal = selected + [{"question_aspect": "B", "chunk_text": "b1"}]
    result = RAGService._ensure_aspect_coverage(selected, internal, aspects, interleave=True)
    assert [p["chunk_text"] for p in result[:2]] == ["a1", "b1"]
    assert result[-1]["source_type"] == "retrieval_gap" and result[-1]["question_aspect"] == "C"
    assert "a2" in [p["chunk_text"] for p in result]


def test_solution_design_gets_a_larger_evidence_budget_only():
    design = answer_style_router.route(DESIGN_QUESTION, KB)
    plain = answer_style_router.route("How does Convergent Invoicing process billable items?", KB)
    assert llm_service._evidence_budget(KB, design) == (16, 12000)
    assert llm_service._evidence_budget(KB, plain) == (12, 9000)


def test_prompt_forbids_blanket_platform_and_performance_claims():
    assert "do not say that all components run on one platform (for example SAP HANA)" in EVIDENCE_AWARE_ANSWER_INSTRUCTIONS
    assert "guarantees real-time rating" in EVIDENCE_AWARE_ANSWER_INSTRUCTIONS


def test_groq_output_reservation_keeps_requests_inside_the_rate_limit(monkeypatch):
    from backend.app.config import settings
    from backend.app.services.llm_service import GROQ_MAX_OUTPUT_TOKENS, GROQ_MIN_OUTPUT_TOKENS

    monkeypatch.setattr(settings, "GROQ_TOKENS_PER_MINUTE", 8000)
    assert llm_service._groq_max_tokens("short prompt") == GROQ_MAX_OUTPUT_TOKENS
    prompt = "x" * 20000  # ~5000 tokens
    reserved = llm_service._groq_max_tokens(prompt)
    assert GROQ_MIN_OUTPUT_TOKENS < reserved < GROQ_MAX_OUTPUT_TOKENS
    assert len(prompt) * 2 // 9 + reserved <= 8000
    assert llm_service._groq_max_tokens("x" * 60000) == GROQ_MIN_OUTPUT_TOKENS


def test_tight_budget_asks_gpt_oss_for_low_reasoning_effort():
    assert "reasoning_effort" not in llm_service._groq_output_args("openai/gpt-oss-120b", "short prompt")
    tight = llm_service._groq_output_args("openai/gpt-oss-120b", "x" * 20000)
    assert tight["reasoning_effort"] == "low" and tight["max_tokens"] < 4096
    assert "reasoning_effort" not in llm_service._groq_output_args("qwen/qwen3.8-27b", "x" * 20000)


def test_zero_width_characters_inside_markers_are_still_markers():
    from backend.app.services.evidence_markers import (
        StreamingMarkerStripper, extract_marker_ids, remove_invalid_markers, strip_markers,
    )

    text = "SOM owns the subscription contract [\u200bE2\u200b]. CC rates usage [\u200bE3\u200b, E4]."
    assert extract_marker_ids(text) == ["E2", "E3", "E4"]
    assert strip_markers(text) == "SOM owns the subscription contract. CC rates usage."
    assert remove_invalid_markers(text, {"E2", "E3"}) == "SOM owns the subscription contract [E2]. CC rates usage [E3]."
    stripper = StreamingMarkerStripper()
    streamed = "".join(stripper.feed(ch) for ch in text) + stripper.flush()
    assert "E2" not in streamed and "\u200b" not in streamed
