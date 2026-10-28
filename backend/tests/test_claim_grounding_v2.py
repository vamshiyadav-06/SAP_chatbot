"""Claim-level grounding, citation correctness, confidence scoring and safe degradation (offline)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.config import settings
from backend.app.services.grounding_service import GroundingService, grounding_service
from backend.app.services import confidence_scoring
from backend.app.services.answer_guard import apply_guard, UNRESOLVED_HEADING
from backend.app.services.evidence_markers import (
    StreamingMarkerStripper,
    assign_evidence_ids,
    extract_marker_ids,
    remove_invalid_markers,
    strip_markers,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bp_block_reference_evidence.json"


@pytest.fixture()
def reference():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assign_evidence_ids(data["passages"])
    return data


# --- citations ------------------------------------------------------------------------

def test_citation_must_point_at_the_passage_that_supports_the_claim(reference):
    answer = (
        "Postings to a contract account can be prevented by a central posting block [E4]. "
        "Postings to a contract account can be prevented by a central posting block [E3]."
    )
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    statuses = [c["citation_status"] for c in result["claims"]]
    assert statuses == ["correct", "mismatch"]
    assert result["citation_checks"]["mismatched"] == 1
    assert result["claims"][1]["status"] == "citation_mismatch"


def test_whole_document_citation_does_not_prove_an_unstated_claim(reference):
    # E1 is about blocked customers/suppliers, but it does not say XK02 removes the block.
    answer = "Use transaction XK02 to remove the supplier block [E1]."
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert result["claims"][0]["citation_status"] == "mismatch"
    assert result["passes_grounding_gate"] is False


def test_invalid_marker_ids_are_reported_and_removed(reference):
    result = grounding_service.verify_answer(
        reference["question"], "Lock reasons can be defined in Customizing [E9].", reference["passages"])
    assert "E9" in result["citation_checks"]["invalid_ids"]
    assert remove_invalid_markers("Text [E9] and [E1, E9].", {"E1"}) == "Text and [E1]."


def test_marker_after_punctuation_stays_with_its_claim(reference):
    answer = "Lock reasons can be defined in Customizing. [E4] All locks can be given a time limit. [E4]"
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert [c["cited_evidence_ids"] for c in result["claims"]] == [["E4"], ["E4"]]


# --- claim types ------------------------------------------------------------------------

def test_unsupported_causal_effect_of_removing_a_block_is_critical(reference):
    answer = "Removing the block will automatically release all pending invoices for billing."
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert result["claims"][0]["status"] == "unsupported_causal"
    assert any(f["status"] == "unsupported_effect" for f in result["critical_failures"])
    assert result["passes_grounding_gate"] is False


def test_supported_causal_relationship_is_accepted():
    passages = [{"chunk_text": "Open items in a blocked contract account are not dunned because the central posting block prevents dunning."}]
    result = grounding_service.verify_answer(
        "dunning", "Open items are not dunned because the central posting block prevents dunning.", passages)
    assert result["unsupported_causal_claims"] == []


def test_contradicted_claims_are_populated_and_fail_the_gate(reference):
    result = grounding_service.verify_answer(
        reference["question"], "In S/4HANA, use FD02 to remove the customer block.", reference["passages"])
    assert result["contradicted_claims"]
    assert result["passes_grounding_gate"] is False


def test_partially_supported_answer_keeps_verified_parts(reference):
    answer = (
        "Postings to a contract account can be prevented by a central posting block [E4]. "
        "Lock reasons can be defined in Customizing [E4]. "
        "Use transaction BUP3 to remove the business partner block."
    )
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert len(result["supported_claims"]) == 2
    assert any(f["identifier"] == "BUP3" for f in result["critical_failures"])
    assert result["passes_grounding_gate"] is False


def test_limitations_and_clarifications_are_not_counted_as_unsupported(reference):
    answer = (
        "Postings to a contract account can be prevented by a central posting block [E4]. "
        "The retrieved documentation does not establish which transaction removes a Business Partner block. "
        "Which block type do you see, and in which SAP release?"
    )
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert [c["status"] for c in result["claims"]] == ["supported", "qualified", "clarification"]
    assert result["material_claim_count"] == 1
    assert result["passes_grounding_gate"] is True


def test_release_applicability_flags_mismatch():
    passages = [{"evidence_id": "E1", "chunk_text": "In SAP S/4HANA the user interface for customer master data is transaction BP."}]
    result = grounding_service.verify_answer(
        "Which transaction maintains customers in SAP ECC 6.0?",
        "The user interface for customer master data is transaction BP [E1].", passages)
    assert result["claims"][0]["release_applicability"] == "mismatch"


def test_high_overlap_never_overrides_a_failed_critical_claim(reference):
    # Nearly every word comes from the evidence, but the identifier is used for an undocumented operation.
    answer = "Processing locks for the contract account are removed with transaction FKLOCK2 [E4]."
    result = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    assert result["critical_failures"]
    assert result["passes_grounding_gate"] is False


def test_validation_can_be_disabled_for_rollback(reference):
    with patch.object(settings, "TECHNICAL_CLAIM_VALIDATION_ENABLED", False):
        result = GroundingService().verify_answer(
            reference["question"], "Use FKLOCK2 to remove the lock on the contract account.", reference["passages"])
    assert result["critical_failures"] == []
    assert result["technical_validation"] == []


# --- confidence scoring ------------------------------------------------------------------

def test_confidence_components_are_separate_and_capped_by_critical_failures(reference):
    bad = grounding_service.verify_answer(
        reference["question"], "Use transaction XK02 to remove the block [E1].", reference["passages"])
    report = confidence_scoring.build_report(
        retrieval_relevance=0.99, passages=reference["passages"], verification=bad,
        aspects=[{"aspect": "q", "evidence_count": 4}],
    )
    assert set(report["components"]) == {
        "retrieval_relevance", "evidence_coverage", "claim_verification", "source_authority", "technical_validity"}
    assert report["components"]["retrieval_relevance"] == 0.99
    assert report["overall_confidence"] <= settings.CRITICAL_FAILURE_CONFIDENCE_CAP
    assert report["decision"] in ("partial", "rejected")
    assert report["critical_failures"]


def test_confidence_weights_are_configurable(reference):
    good = grounding_service.verify_answer(
        reference["question"], "Lock reasons can be defined in Customizing [E4].", reference["passages"])
    with patch.object(settings, "CONFIDENCE_WEIGHT_RETRIEVAL", 1.0), patch.object(settings, "CONFIDENCE_WEIGHT_COVERAGE", 0.0), \
            patch.object(settings, "CONFIDENCE_WEIGHT_CLAIMS", 0.0), patch.object(settings, "CONFIDENCE_WEIGHT_AUTHORITY", 0.0), \
            patch.object(settings, "CONFIDENCE_WEIGHT_TECHNICAL", 0.0):
        report = confidence_scoring.build_report(retrieval_relevance=0.4, passages=reference["passages"], verification=good)
    assert report["overall_confidence"] == pytest.approx(0.4)
    assert report["decision"] == "accepted"


def test_web_authority_distinguishes_official_from_community():
    official = confidence_scoring.passage_authority({"source_type": "web", "authority_class": "official_sap_help"})
    note = confidence_scoring.passage_authority({"source_type": "web", "authority_class": "sap_support_note"})
    community = confidence_scoring.passage_authority({"source_type": "web", "authority_class": "sap_community"})
    assert official > community and note > community


# --- guard and markers --------------------------------------------------------------------

def test_guard_removes_failed_claims_keeps_verified_ones_and_states_limits(reference):
    answer = (
        "### Where to view it\n"
        "Postings to a contract account can be prevented by a central posting block [E4].\n"
        "### How to remove it\n"
        "1. Use transaction XK02 to remove the block [E1].\n"
        "2. Clear CVP_XBLCK_B directly in table KNB1 using SE16N."
    )
    verification = grounding_service.verify_answer(reference["question"], answer, reference["passages"])
    guarded = apply_guard(answer, verification, allowed_evidence_ids={"E1", "E2", "E3", "E4"},
                          clarification_question="Which block type do you see?")
    text = guarded["answer"]
    assert guarded["applied"] and len(guarded["removed_claims"]) == 2
    assert "central posting block [E4]" in text
    assert "Use transaction XK02" not in text and "SE16N" not in text
    assert "### How to remove it" not in text  # orphaned heading dropped
    assert UNRESOLVED_HEADING in text and text.rstrip().endswith("Which block type do you see?")
    reverified = grounding_service.verify_answer(reference["question"], text, reference["passages"])
    assert reverified["critical_failures"] == []


def test_marker_helpers_and_streaming_stripper():
    text = "Central posting block [E4]. Locks expire [E2, E4]. Keep [Note] and [E] text."
    assert extract_marker_ids(text) == ["E4", "E2"]
    assert strip_markers(text) == "Central posting block. Locks expire. Keep [Note] and [E] text."
    stripper = StreamingMarkerStripper()
    tokens = ["Central posting block [", "E", "4]. Locks expire [E2", ", E4]. Keep [No", "te] and [E] text."]
    streamed = "".join(stripper.feed(t) for t in tokens) + stripper.flush()
    assert streamed.replace(" .", ".") == "Central posting block. Locks expire. Keep [Note] and [E] text."
