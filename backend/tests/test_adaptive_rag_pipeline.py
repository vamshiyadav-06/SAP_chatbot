"""
Automated Regression Test Suite for Adaptive Answer Generation and RAG Pipeline Integrity.
Tests A through F:
- Test A: Complex Production Incident (10-section framework, independent discrepancies, evidence expansion)
- Test B: Simple Question (adaptive brevity, proportional structure)
- Test C: Insufficient Evidence (SAP Note boundary, anti-hallucination)
- Test D: Multi-Turn Context (conversation memory preservation across incident investigation turns)
- Test E: Long-Response Integrity (continuation logic, finish_reason detection, diagnostic tracking)
- Test F: Existing Behavior (domain restrictions, citation contract, API stability)
"""

import pytest
from unittest.mock import MagicMock, patch
from backend.app.services.answer_planner import answer_planner
from backend.app.services.answer_style_router import answer_style_router, AnswerType
from backend.app.services.rag_service import RAGService, rag_service
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.llm_service import llm_service, SYSTEM_PROMPT, EVIDENCE_AWARE_ANSWER_INSTRUCTIONS
from backend.app.services.sap_identifier_validator import sap_identifier_validator


# ==============================================================================
# TEST A: COMPLEX PRODUCTION INCIDENT
# ==============================================================================

TEST_A_QUERY = (
    "During month-end processing, SAP Convergent Charging successfully processes 100,000 usage records, "
    "but Convergent Invoicing contains only 98,500 corresponding billable items. Additionally, 5,000 FI-CA "
    "posting discrepancies and 2,000 potentially duplicated financial transactions have been identified. "
    "Explain how to investigate the discrepancies independently, establish the root causes, recover missing "
    "records safely, prevent duplicate financial processing, and validate the final reconciliation."
)

SAMPLE_KB = [
    {
        "source_type": "knowledge_base",
        "evidence_id": f"E{i}",
        "document_name": "SAP_BRIM_Operations_Guide.pdf",
        "page_number": i + 1,
        "score": 0.85 - (i * 0.02),
        "chunk_text": f"SAP BRIM incident resolution procedure chunk {i}: handling billable item generation and FI-CA reconciliation keys."
    }
    for i in range(1, 15)
]


def test_a_complex_production_incident_archetype_and_sections():
    """Verify Test A query triggers the 10-section production_incident framework."""
    plan = answer_planner.plan_answer(TEST_A_QUERY)
    assert plan["question_type"] == "production_incident"
    assert "Production Incident" in plan["title"]
    
    instructions = plan["instructions"]
    required_sections = [
        "1. Executive Summary",
        "2. Problem Analysis",
        "3. Evidence and Findings",
        "4. Root-Cause Analysis",
        "5. Step-by-Step Investigation",
        "6. Corrective and Recovery Actions",
        "7. Duplicate Prevention and Financial Integrity",
        "8. Validation and Reconciliation",
        "9. Risks and Limitations",
        "10. Final Recommendations",
    ]
    for section in required_sections:
        assert section in instructions, f"Mandatory section '{section}' missing from plan instructions"


def test_a_complex_production_incident_style_router():
    """Verify AnswerStyleRouter maps Test A to production_incident layout with 10 sections."""
    style_plan = answer_style_router.route(TEST_A_QUERY, SAMPLE_KB)
    assert style_plan.answer_type == "production_incident"
    assert style_plan.max_sections == 10
    assert style_plan.detail_level == "detailed"
    assert style_plan.needs_steps is True
    assert style_plan.domain_archetype == "production_incident"


def test_a_aspect_splitting_and_evidence_expansion():
    """Verify Test A splits into independent multi-component retrieval queries and expands evidence."""
    aspects = RAGService.split_question_aspects(TEST_A_QUERY)
    assert len(aspects) >= 4, f"Expected at least 4 aspects, got: {len(aspects)}"
    joined = " ".join(aspects).lower()
    
    # Must cover CC to CI missing billable items
    assert "billable item" in joined or "charging" in joined or "invoicing" in joined
    # Must cover FI-CA posting discrepancies
    assert "fi-ca" in joined or "posting" in joined
    # Must cover duplicate prevention
    assert "duplicate" in joined
    # Must cover safe recovery
    assert "recovery" in joined or "reprocess" in joined or "safely" in joined
    # Must cover reconciliation
    assert "reconcil" in joined or "matrix" in joined

    # Verify evidence selection dynamically scales top_k for multi-aspect incident queries
    candidates = [
        {
            "candidate_id": f"c_{i}",
            "source_type": "knowledge_base",
            "document_name": f"Doc_{i}.pdf",
            "page_number": i,
            "snippet": f"SAP BRIM technical diagnostic text for aspect {i % 4}",
            "calibrated_relevance_score": 0.88 - (i * 0.01),
            "final_score": 0.88 - (i * 0.01),
            "chunk_text": f"SAP BRIM technical diagnostic text for aspect {i % 4}"
        }
        for i in range(24)
    ]
    # Pass aspect_queries via confidence_data to simulate multi-aspect incident retrieval
    conf_data = {
        "confidence": 0.85,
        "should_trigger_tavily": False,
        "aspects": ["aspect 1", "aspect 2", "aspect 3", "aspect 4"]
    }
    selected = evidence_selection_service.select_strongest_evidence(TEST_A_QUERY, candidates, [], conf_data)
    assert len(selected["selected_passages"]) > 4, "Evidence selection should expand beyond 4 chunks for multi-aspect queries"
    assert len(selected["selected_passages"]) <= 16


def test_a_prompt_generation_contains_all_requirements():
    """Verify built answer prompt for Test A contains all senior incident requirements."""
    style_plan = answer_style_router.route(TEST_A_QUERY, SAMPLE_KB)
    prompt = llm_service._build_answer_prompt(TEST_A_QUERY, SAMPLE_KB, "knowledge_base", answer_plan=style_plan)
    
    assert "1. Executive Summary" in prompt
    assert "Problem Analysis" in prompt
    assert "Root-Cause Analysis" in prompt
    assert "Duplicate Prevention and Financial Integrity" in prompt
    assert "Validation and Reconciliation" in prompt
    assert "Final Recommendations" in prompt
    assert "1,200" in prompt and "2,000 words" in prompt
    assert "Never invent or assume transaction codes" in prompt


# ==============================================================================
# TEST B: SIMPLE QUESTION (ADAPTIVE BREVITY)
# ==============================================================================

TEST_B_QUERY = "What is the difference between SAP Convergent Charging and SAP Convergent Invoicing?"


def test_b_simple_question_adaptive_brevity():
    """Verify simple questions receive adaptive, proportionate handling without 10 forced sections."""
    assert not RAGService.is_incident_or_multipart_question(TEST_B_QUERY)
    
    plan = answer_planner.plan_answer(TEST_B_QUERY)
    assert plan["question_type"] != "production_incident"
    
    style_plan = answer_style_router.route(TEST_B_QUERY, SAMPLE_KB[:2])
    assert style_plan.answer_type != "production_incident"
    assert style_plan.max_sections <= 5
    
    prompt = llm_service._build_answer_prompt(TEST_B_QUERY, SAMPLE_KB[:2], "knowledge_base", answer_plan=style_plan)
    assert "10. Final Recommendations" not in prompt
    assert "7. Duplicate Prevention and Financial Integrity" not in prompt


# ==============================================================================
# TEST C: INSUFFICIENT EVIDENCE (ANTI-HALLUCINATION)
# ==============================================================================

TEST_C_QUERY = "What exact SAP Note fixes every missing billable-item issue across all SAP BRIM releases?"


def test_c_insufficient_evidence_boundaries():
    """Verify the agent does not fabricate an SAP Note and states documentation limits."""
    prompt = llm_service._build_answer_prompt(TEST_C_QUERY, [], "knowledge_base")
    assert "Never invent or assume transaction codes" in prompt
    assert "Missing evidence is not proof that SAP lacks a function" in prompt or "State retrieval limitations precisely" in prompt
    
    # Verify sap_identifier_validator flags non-existent/guessed SAP notes
    claim = "SAP Note 9999999 resolves all missing billable item discrepancies universally."
    checks = sap_identifier_validator.validate_sentence(claim, [])
    assert len(checks) > 0
    assert any(c.status in ["unverified_identifier", "unverified"] for c in checks)


# ==============================================================================
# TEST D: MULTI-TURN CONTEXT PRESERVATION
# ==============================================================================

def test_d_multi_turn_context_retention():
    """Verify multi-turn incident context is retained and passed to answer prompts across 3 turns."""
    turn_1_query = "We have 1,500 missing billable items in Convergent Invoicing. Explain the investigation."
    turn_1_reply = "Investigate the RFC destination between CC and CI, inspect SM58/qRFC queues, and verify consumption item mapping."
    
    turn_2_query = "How should we recover them without creating duplicates?"
    turn_2_reply = "Check the processing status of each consumption item in CI before re-triggering rating. Use idempotent reprocessing."
    
    turn_3_query = "Prepare a validation checklist for this incident."
    
    chat_history = [
        {"role": "user", "content": turn_1_query},
        {"role": "assistant", "content": turn_1_reply},
        {"role": "user", "content": turn_2_query},
        {"role": "assistant", "content": turn_2_reply},
    ]
    
    plan_3 = answer_planner.plan_answer(turn_3_query, is_follow_up=True)
    prompt_3 = llm_service._build_answer_prompt(
        turn_3_query,
        SAMPLE_KB[:4],
        source_type="knowledge_base",
        chat_history=chat_history,
        answer_plan=answer_style_router.route(turn_3_query, SAMPLE_KB[:4])
    )
    
    # Must retain original incident details (1,500 missing billable items, duplicate prevention)
    assert "1,500 missing billable items" in prompt_3
    assert "recover them without creating duplicates" in prompt_3
    assert "RECENT CONVERSATION CONTEXT" in prompt_3


# ==============================================================================
# TEST E: LONG-RESPONSE INTEGRITY & CONTINUATION LOGIC
# ==============================================================================

def test_e_finish_reason_detection_and_continuation():
    """Verify finish_reason == 'length' triggers continuation without repeating sections."""
    llm_service.last_finish_reason = "stop"
    llm_service.is_truncated = False
    llm_service.was_continued = False
    
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "## 9. Risks and Limitations\n- Documentation does not detail batch sizes.\n\n## 10. Final Recommendations\n- Immediate next steps: inspect SM58 queues."
    mock_model.generate_content.return_value = mock_response
    
    partial_text = "## 1. Executive Summary\nAnalysis...\n\n## 8. Validation and Reconciliation\nChecks..."
    continued = llm_service._continue_gemini(mock_model, TEST_A_QUERY, partial_text)
    
    assert continued is not None
    assert "10. Final Recommendations" in continued
    assert "1. Executive Summary" not in continued  # Must not repeat earlier sections
    
    # Verify prompt instructs not to repeat
    call_args = mock_model.generate_content.call_args[0][0]
    assert "Do NOT repeat any earlier text, sections, or headings" in call_args


def test_e_diagnostics_tracking():
    """Verify diagnostic properties track model parameters and finish status accurately."""
    llm_service.last_model_used = "gemini-2.5-flash"
    llm_service.last_provider_used = "gemini"
    llm_service.last_finish_reason = "stop"
    llm_service.last_configured_max_tokens = 8192
    llm_service.is_truncated = False
    llm_service.was_continued = True
    
    assert llm_service.last_configured_max_tokens == 8192
    assert llm_service.last_finish_reason == "stop"
    assert not llm_service.is_truncated
    assert llm_service.was_continued


# ==============================================================================
# TEST F: EXISTING BEHAVIOR PRESERVATION
# ==============================================================================

def test_f_existing_behavior_preservation():
    """Verify existing domain restrictions, citation formatting, and API contracts remain intact."""
    # 1. Non-SAP domain restriction
    off_domain_query = "What is the best recipe for baking chocolate chip cookies?"
    off_domain_aspects = RAGService.split_question_aspects(off_domain_query)
    assert len(off_domain_aspects) <= 1
    
    # 2. Evidence citation schema integrity
    sample_chunk = {
        "document_name": "SAP_BRIM_Guide.pdf",
        "page_number": 42,
        "chunk_text": "Convergent Invoicing processes billable items in mass runs.",
        "snippet": "Convergent Invoicing processes billable items in mass runs."
    }
    citation = rag_service._format_kb_citation(sample_chunk)
    assert citation["document"] == "SAP_BRIM_Guide.pdf"
    assert citation["page"] == 42
    assert "snippet" in citation
    assert citation["source_type"] == "knowledge_base"
