"""
Unit Tests for Phase 1: Corpus and Metadata.
Verifies:
- Document tier table mapping and bug fixes (AI files, summaries are self_authored)
- Corpus identifier index exact strings (no normalization)
- Off-domain document flags and exclusion logic
- Chunk module tagging (SOM, CM, CC, CI, FI-CA, RAR, General)
- Safe official document ingestion requiring licence confirmation
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.app.config import settings
from backend.app.corpus.tier_definitions import DOCUMENT_TIER_MAPPING
from backend.app.corpus.module_tagger import tag_chunk_modules
from backend.app.corpus.identifier_indexer import extract_chunk_identifiers
from backend.app.services.corpus_service import corpus_service
from backend.app.services.context_packing_service import context_packing_service


def test_document_tier_mapping_correctness():
    """Verify document tiers conform to Phase 1 rules and fix previous mapping bugs."""
    # AI-authored or summary files MUST be self_authored
    assert DOCUMENT_TIER_MAPPING["SAP BRIM AI Architect.pdf"]["tier"] == "self_authored"
    assert DOCUMENT_TIER_MAPPING["BRIM Q Bank.pdf"]["tier"] == "self_authored"
    assert DOCUMENT_TIER_MAPPING["100  Ans.pdf"]["tier"] == "self_authored"
    assert DOCUMENT_TIER_MAPPING["100 4 ans.pdf"]["tier"] == "self_authored"
    assert DOCUMENT_TIER_MAPPING["100 Ans 2.pdf"]["tier"] == "self_authored"
    assert DOCUMENT_TIER_MAPPING["SAP_BRIM_End_to_End_Integration_and_SPRO_Cookbook.pdf"]["tier"] == "self_authored"

    # Official SAP courseware and guides
    assert DOCUMENT_TIER_MAPPING["BR234_EN_SOM 2.pdf"]["tier"] == "official_sap"
    assert DOCUMENT_TIER_MAPPING["BRIM_AC240_EN_Col16.pdf"]["tier"] == "official_sap"
    assert DOCUMENT_TIER_MAPPING["pdfdownload.pdf"]["tier"] == "official_sap"
    assert DOCUMENT_TIER_MAPPING["SAP CC.pdf"]["tier"] == "official_sap"

    # Published books
    assert DOCUMENT_TIER_MAPPING["SAP BRIM Press Book 2nd Edition - Expertsoft.pdf"]["tier"] == "sap_partner_or_book"
    assert DOCUMENT_TIER_MAPPING["Authorizations-in-S4-HANA-and-Fiori.pdf"]["tier"] == "sap_partner_or_book"

    # Community forum
    assert DOCUMENT_TIER_MAPPING["Budget billing.pdf"]["tier"] == "forum"


def test_off_domain_flags_coverage():
    """Verify off-domain documents are correctly flagged without being deleted."""
    off_domain_docs = [
        "SIMPL_OP1709.pdf",
        "Authorizations-in-S4-HANA-and-Fiori.pdf",
        "E_Book_ABAP_RESTful_Programming_Model_2020_Rel_NW_wwwERPExamsCom.pdf",
        "SAP_ABAP_Development_and_RAP_Standards.pdf",
        "SAP_Basis_Administration_and_Security_Handbook.pdf",
        "SAP_CO_Controlling_Configuration_Handbook.pdf",
        "SAP_FI_Financial_Accounting_Guide.pdf",
        "SAP_Fiori_Design_and_Deployment_Manual.pdf",
        "SAP_HCM_Human_Capital_Management_Guide.pdf",
        "SAP_MM_Materials_Management_Manual.pdf",
        "SAP_PP_Production_Planning_Reference.pdf",
        "SAP_S4HANA_Architecture_and_Migration_Guide.pdf",
        "SAP_SD_Sales_and_Distribution_Handbook.pdf",
        "SAP-PRESS-Catalog-Shop.pdf"
    ]
    for doc in off_domain_docs:
        assert corpus_service.is_document_off_domain(doc) is True, f"{doc} should be marked off-domain"

    # In-domain documents must NOT be marked off-domain
    in_domain_docs = [
        "BR234_EN_SOM 2.pdf",
        "BRIM_AC240_EN_Col16.pdf",
        "SAP CC.pdf",
        "SAP CI1.pdf",
        "SAP BRIM Press Book 2nd Edition - Expertsoft.pdf",
        "pdfdownload.pdf"
    ]
    for doc in in_domain_docs:
        assert corpus_service.is_document_off_domain(doc) is False, f"{doc} should be in-domain"


def test_corpus_identifier_index_exact_strings():
    """Verify exact strings only (no normalization, case preserved)."""
    index = corpus_service.get_identifier_index()
    assert len(index) > 0

    # Test key exact identifiers
    expected_exact = ["DFKKOP", "FPL9", "DFKKBIXBIT2", "FKKBIXBIT_MON", "SPRO"]
    for ident in expected_exact:
        assert corpus_service.is_identifier_in_corpus(ident) is True, f"Missing exact identifier {ident}"
        details = corpus_service.get_identifier_details(ident)
        assert details["identifier"] == ident  # Exact casing preserved
        assert details["type"] in ("table", "tcode", "report_or_fm", "technical_object")
        assert len(details["chunk_ids"]) > 0

    # Ensure fake identifier is not found
    assert corpus_service.is_identifier_in_corpus("NON_EXISTENT_SAP_OBJECT_999") is False


def test_chunk_module_tagging():
    """Verify multi-module tagging on sample domain texts."""
    # SOM + CC chunk
    text1 = "Subscription order in SOM triggers ODI distribution to create a charging contract with a charge plan in SAP CC."
    mods1, prim1 = tag_chunk_modules(text1)
    assert "SOM" in mods1
    assert "CC" in mods1

    # FI-CA chunk
    text2 = "Open items in table DFKKOP are cleared via transaction FPL9 using account balance clearing control."
    mods2, prim2 = tag_chunk_modules(text2)
    assert "FI-CA" in mods2
    assert prim2 == "FI-CA"

    # RAR chunk
    text3 = "Revenue accounting item (RAI) in FARR_RAI_MON creates a performance obligation (POB) under IFRS 15."
    mods3, prim3 = tag_chunk_modules(text3)
    assert "RAR" in mods3
    assert prim3 == "RAR"


def test_context_packing_tier_inference_bug_fix():
    """Verify context_packing_service uses the corrected tier mapping."""
    # AI Architect must be self_authored
    t1 = context_packing_service.infer_chunk_tier({"document_name": "SAP BRIM AI Architect.pdf"})
    assert t1 == "self_authored"

    # Q Bank must be self_authored
    t2 = context_packing_service.infer_chunk_tier({"document_name": "BRIM Q Bank.pdf"})
    assert t2 == "self_authored"

    # 100 Ans must be self_authored
    t3 = context_packing_service.infer_chunk_tier({"document_name": "100 Ans 2.pdf"})
    assert t3 == "self_authored"

    # Press book must be sap_partner_or_book
    t4 = context_packing_service.infer_chunk_tier({"document_name": "SAP BRIM Press Book 2nd Edition - Expertsoft.pdf"})
    assert t4 in ("sap_partner_or_book", "book")

    # Courseware must be official_sap
    t5 = context_packing_service.infer_chunk_tier({"document_name": "BR234_EN_SOM 2.pdf"})
    assert t5 == "official_sap"


def test_synthetic_pdf_generators_do_not_claim_official_or_confidential_status():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sap_generator = (root / "generate_sap_docs.py").read_text(encoding="utf-8")
    brim_generator = (root / "generate_brim_master_docs.py").read_text(encoding="utf-8")
    assert "CONFIDENTIAL & PROPRIETARY" not in sap_generator
    assert "OFFICIAL REFERENCE MANUAL" not in sap_generator
    assert "Enterprise Official Technical Handbook" not in brim_generator


def test_safe_official_ingestion_licence_gate():
    """Verify official document ingestion strictly fails without licence confirmation."""
    with pytest.raises(PermissionError) as exc_info:
        corpus_service.ingest_official_document(
            file_path=Path("dummy_official_sap.pdf"),
            licence_confirmed=False
        )
    assert "licence must be confirmed" in str(exc_info.value).lower()
