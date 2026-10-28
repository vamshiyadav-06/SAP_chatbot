"""Unit tests for claim-level SAP technical identifier validation (offline, no DB, no LLM)."""

import json
from pathlib import Path

import pytest

from backend.app.services.sap_identifier_validator import (
    CRITICAL_STATUSES,
    extract_identifiers,
    extract_navigation_paths,
    sap_identifier_validator as validator,
)
from backend.app.services.restriction_scope_classifier import restriction_scope_classifier, CATEGORIES

FIXTURE = Path(__file__).parent / "fixtures" / "bp_block_reference_evidence.json"


@pytest.fixture(scope="module")
def reference():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for i, p in enumerate(data["passages"]):
        p["evidence_id"] = f"E{i + 1}"
    return data


def checks_for(sentence, reference):
    return validator.validate_sentence(sentence, reference["passages"], query=reference["question"])


def status_of(sentence, identifier, reference):
    return next(c.status for c in checks_for(sentence, reference) if c.identifier == identifier)


# --- extraction -------------------------------------------------------------------------

def test_extracts_transactions_tables_fields_and_typed_short_codes():
    idents = {i.value: i.id_type for i in extract_identifiers(
        "Use transaction BP or XK02; table KNB1 has field CVP_XBLCK_B; see KNB1-SPERR and SAP Note 2502552."
    )}
    assert idents["BP"] == "transaction"
    assert "XK02" in idents
    assert idents["KNB1"] in ("table", "identifier")
    assert idents["CVP_XBLCK_B"] == "field"
    assert idents["KNB1-SPERR"] == "table_field"
    assert idents["NOTE 2502552"] == "sap_note"


def test_extraction_ignores_standards_releases_and_prose():
    found = {i.value for i in extract_identifiers(
        "Revenue under IFRS15 and ASC606 in S/4HANA 2023 FPS02, SP12, P99 latency, E2E flow in FI-CA."
    )}
    assert not found & {"IFRS15", "ASC606", "SP12", "P99", "E2E", "FI-CA"}


def test_extracts_navigation_paths_with_lead_in_removed():
    paths = extract_navigation_paths("Go to SPRO -> Financial Accounting -> Business Partner -> Unblock")
    assert paths == [["SPRO", "Financial Accounting", "Business Partner", "Unblock"]]


# --- operation claims ------------------------------------------------------------------

def test_transaction_mentioned_for_a_different_operation_is_not_evidence(reference):
    # FKLOCK2 is documented for *creating* processing locks, not removing them.
    assert status_of("You can create processing locks with transaction FKLOCK2.", "FKLOCK2", reference) == "verified"
    assert status_of("Use FKLOCK2 to remove the lock on the contract account.", "FKLOCK2", reference) == "operation_not_evidenced"


def test_operation_object_must_match_not_just_the_verb(reference):
    # Evidence: XK02 removes the *assignment of a blocked supplier to a plant*, not "the block".
    status = status_of("Use transaction XK02 to remove the block from the supplier.", "XK02", reference)
    assert status in CRITICAL_STATUSES


def test_recommending_transaction_listed_as_unavailable_is_contradicted(reference):
    assert status_of("Run FD02 and clear the posting block flag for the customer.", "FD02", reference) == "contradicted"


def test_release_scoped_claim_is_not_contradicted_by_s4_unavailability():
    passages = [{"evidence_id": "E1", "chunk_text": "Transactions XK01, XK02, XK03 are not available in SAP S/4HANA on-premise."}]
    checks = validator.validate_sentence("In SAP ECC, use XK02 to change the supplier.", passages, query="")
    assert next(c for c in checks if c.identifier == "XK02").status != "contradicted"


def test_documented_use_and_documented_unavailability_produce_conflict(reference):
    sentence = "The assignment of a blocked supplier to a plant can be removed via transaction XK02."
    assert status_of(sentence, "XK02", reference) == "conflicting_evidence"
    conflicts = validator.detect_evidence_conflicts(reference["passages"])
    xk02 = next(c for c in conflicts if c["identifier"] == "XK02")
    assert xk02["documented_use_in"] == ["E1"] and "E2" in xk02["unavailable_in"]


def test_identifier_absent_from_evidence_is_unverified_not_invalid():
    checks = validator.validate_sentence(
        "Use transaction BUP3 to remove the block.", [{"evidence_id": "E1", "chunk_text": "Unrelated FI-CA text."}]
    )
    check = next(c for c in checks if c.identifier == "BUP3")
    assert check.status == "unverified_procedure"
    assert "does not mean the identifier is invalid" in check.reason
    assert "invalid" not in check.status


def test_known_registry_object_is_not_evidence_for_the_claim():
    # SLG1 is in the curated registry, but no passage supports the claimed operation.
    checks = validator.validate_sentence(
        "Use SLG1 to remove the business partner block.", [{"evidence_id": "E1", "chunk_text": "Billing documents are created."}]
    )
    check = next(c for c in checks if c.identifier == "SLG1")
    assert check.registry_known is True
    assert check.critical is True


# --- field meaning ---------------------------------------------------------------------

def test_field_meaning_cannot_be_widened_beyond_evidence_scope(reference):
    assert status_of("The field CVP_XBLCK_B is the universal blocking indicator for a Business Partner.",
                     "CVP_XBLCK_B", reference) == "overgeneralized_meaning"
    assert status_of("CVP_XBLCK_B is the central operational block for all business processes.",
                     "CVP_XBLCK_B", reference) == "overgeneralized_meaning"


def test_field_meaning_stated_within_evidence_scope_is_verified(reference):
    assert status_of("In table KNB1, the customer is blocked when the field CVP_XBLCK_B is set.",
                     "CVP_XBLCK_B", reference) == "verified"


def test_field_meaning_is_never_inferred_from_its_name():
    checks = validator.validate_sentence("The field ZZ_BLOCK_FLAG indicates a dunning block.",
                                         [{"evidence_id": "E1", "chunk_text": "Dunning runs evaluate items."}])
    assert next(c for c in checks if c.identifier == "ZZ_BLOCK_FLAG").status == "meaning_not_evidenced"


# --- paths, unsafe procedures, qualifications --------------------------------------------

def test_invented_navigation_path_is_unverified(reference):
    checks = checks_for("Go to SPRO -> Cross-Application Components -> SAP Business Partner -> Unblock Partner.", reference)
    assert any(c.claim_type == "navigation_path" and c.status == "unverified_path" for c in checks)


def test_documented_navigation_path_is_verified(reference):
    checks = checks_for(
        "You can list locks under Accounting -> Financial Accounting -> Contract Accounts Receivable and Payable -> "
        "Periodic Processing -> For Contract Accounts -> Evaluation of Business Blocks.", reference)
    assert any(c.claim_type == "navigation_path" and c.status == "verified" for c in checks)


@pytest.mark.parametrize("sentence", [
    "Clear CVP_XBLCK_B directly in table KNB1 using SE16N.",
    "Open SE16N and untick the block indicator.",
    "Run UPDATE KNB1 SET CVP_XBLCK_B = '' for the customer.",
])
def test_direct_database_updates_are_unsafe(sentence, reference):
    assert any(c.status == "unsafe_procedure" for c in checks_for(sentence, reference))


def test_advice_against_database_updates_is_not_flagged(reference):
    checks = checks_for("Do not update table KNB1 directly in SE16N.", reference)
    assert not any(c.critical for c in checks)


def test_explicit_limitation_statement_is_qualified(reference):
    checks = checks_for("Whether XK02 removes a BP block could not be verified from the retrieved documentation.", reference)
    assert all(c.status == "qualified" for c in checks)


def test_availability_claim_matching_evidence_is_verified(reference):
    checks = checks_for("XK02 and FD02 are not available in SAP S/4HANA on-premise.", reference)
    assert {c.identifier: c.status for c in checks} == {"XK02": "verified", "FD02": "verified"}


# --- restriction scope classification ----------------------------------------------------

def test_generic_bp_block_question_is_ambiguous_across_block_types(reference):
    scope = restriction_scope_classifier.classify(reference["question"])
    assert scope.is_restriction_query and scope.ambiguous
    for key in ("bp_general_status", "customer_master_block", "supplier_master_block", "company_code_restriction",
                "sales_area_restriction", "purchasing_org_restriction", "fica_contract_account_restriction",
                "posting_restriction", "dunning_restriction"):
        assert key in scope.candidate_categories
    assert scope.clarification_question and scope.clarification_question.endswith(".")
    assert all(q.endswith("?") for q in scope.evidence_needed)


@pytest.mark.parametrize("query,expected", [
    ("How do I remove a dunning block on a contract account in FI-CA?", {"fica_contract_account_restriction", "dunning_restriction"}),
    ("The supplier is blocked for purchasing organization 1000", {"supplier_master_block", "purchasing_org_restriction"}),
    ("Customer has an order block in sales area 1000/10/00", {"customer_master_block", "sales_area_restriction"}),
    ("Customer is blocked for posting in company code 1000", {"customer_master_block", "company_code_restriction", "posting_restriction"}),
    ("Invoicing lock prevents the billing run for billable items", {"billing_invoicing_error"}),
])
def test_specific_block_types_are_distinguished(query, expected):
    scope = restriction_scope_classifier.classify(query)
    assert scope.is_restriction_query and not scope.ambiguous
    assert expected <= set(scope.explicit_categories)


def test_non_block_questions_are_not_classified():
    assert not restriction_scope_classifier.classify("Explain convergent invoicing billable item classes").is_restriction_query


def test_prompt_guidance_names_every_block_type_and_forbids_db_edits(reference):
    guidance = restriction_scope_classifier.classify(reference["question"]).prompt_guidance()
    for category in CATEGORIES:
        assert category.label in guidance
    assert "SE16N" in guidance and "not interchangeable" in guidance.lower()
