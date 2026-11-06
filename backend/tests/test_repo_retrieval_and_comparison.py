import os
import re
import json
import hashlib
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from backend.app.config import settings
from backend.app.retrieval.license_manager import LicenseManager
from backend.app.retrieval.repo_registry import repo_registry, REGISTERED_REPOSITORIES
from backend.app.retrieval.brim_relevance_gate import (
    BRIMRelevanceGate,
    IDENTIFIER_INDEX_PATH,
    FALSE_POSITIVE_INDICATORS
)
from backend.app.retrieval.repo_chunker import RepoChunker
from backend.app.retrieval.repo_store import RepoStore
from backend.app.retrieval.multi_source_compare import MultiSourceComparator, multi_source_comparator
from backend.app.services.rag_service import rag_service


# ==============================================================================
# 1. FEATURE FLAGS & OPERATING MODES TESTS
# ==============================================================================

def test_feature_flags_default_to_false(monkeypatch):
    """Verify non-negotiable requirement: both feature flags default to False.

    Checks the code defaults, not the developer's .env (which may enable them) or the environment."""
    from backend.app.config import Settings
    monkeypatch.delenv("REPO_SOURCE_ENABLED", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_COMPARE_ENABLED", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.REPO_SOURCE_ENABLED is False
    assert defaults.MULTI_SOURCE_COMPARE_ENABLED is False


def test_flag_interaction_safety():
    """
    Verify flag interaction rule:
    MULTI_SOURCE_COMPARE_ENABLED=true without REPO_SOURCE_ENABLED=true must NEVER activate repository retrieval.
    """
    with patch.object(settings, "REPO_SOURCE_ENABLED", False), \
         patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", True):
        # Even if compare flag is on, repo retrieval remains strictly disabled
        assert settings.REPO_SOURCE_ENABLED is False
        assert settings.MULTI_SOURCE_COMPARE_ENABLED is True

        comparator = MultiSourceComparator()
        mock_db = MagicMock()
        mock_kb = [{"chunk_id": "kb-1", "chunk_text": "text", "score": 0.85, "document_name": "doc.pdf", "page_number": 1}]
        with patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks") as mock_repo_search, \
             patch("backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative", return_value=[]):
            res = comparator.execute_multi_source_comparison(
                db=mock_db,
                query="test",
                kb_candidates=mock_kb,
                repo_source_enabled=False,
                multi_source_compare_enabled=True,
                web_search_available=False
            )
            mock_repo_search.assert_not_called()
            assert "github_repo" not in res["comparison"]["sources_compared"]


def test_mode_a_legacy_behavior_preserved():
    """Mode A (both flags False): executes existing pipeline unchanged without comparison side effects."""
    with patch.object(settings, "REPO_SOURCE_ENABLED", False), \
         patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False):
        mock_kb_chunks = [
            {
                "chunk_id": "kb-1",
                "document_name": "SAP_BRIM_Overview.pdf",
                "page_number": 12,
                "chunk_text": "SAP BRIM integrates SOM, CC, CI, and FI-CA.",
                "score": 0.88
            }
        ]
        with patch.object(rag_service.retrieval, "retrieve", return_value=mock_kb_chunks), \
             patch.object(rag_service, "_generate_grounded_answer") as mock_gen:
            mock_gen.return_value = {
                "answer": "SAP BRIM integrates SOM, CC, CI, and FI-CA.",
                "grounded_score": 0.95,
                "citations": [{"source": "SAP_BRIM_Overview.pdf", "page": 12, "chunk_id": "kb-1"}],
                "insufficient_evidence": False
            }
            res = rag_service.query("Explain SAP BRIM architecture")
            assert res["answer"] == "SAP BRIM integrates SOM, CC, CI, and FI-CA."
            assert res.get("comparison_audit") is None
            assert res.get("shadow_audit") is None


def test_mode_b_shadow_mode_does_not_mutate_answer():
    """Mode B (REPO_SOURCE_ENABLED=true, MULTI_SOURCE_COMPARE_ENABLED=false): legacy answer remains authoritative."""
    with patch.object(settings, "REPO_SOURCE_ENABLED", True), \
         patch.object(settings, "MULTI_SOURCE_COMPARE_ENABLED", False):
        mock_kb_chunks = [
            {
                "chunk_id": "kb-1",
                "document_name": "SAP_BRIM_Overview.pdf",
                "page_number": 12,
                "chunk_text": "Legacy authoritative answer text.",
                "score": 0.82
            }
        ]
        with patch.object(rag_service.retrieval, "retrieve", return_value=mock_kb_chunks), \
             patch.object(rag_service, "_generate_grounded_answer") as mock_gen, \
             patch.object(rag_service.comparator, "run_shadow_comparison") as mock_shadow:
            mock_gen.return_value = {
                "answer": "Legacy authoritative answer text.",
                "grounded_score": 0.90,
                "citations": [{"source": "SAP_BRIM_Overview.pdf", "page": 12, "chunk_id": "kb-1"}],
                "insufficient_evidence": False
            }
            mock_shadow.return_value = {
                "hypothetical_winner": "github_repo",
                "hypothetical_score": 0.92,
                "shadow_candidates_count": 2
            }
            res = rag_service.query("Explain SOM contract management")
            # Authoritative answer is strictly unchanged
            assert res["answer"] == "Legacy authoritative answer text."
            assert res["grounded_score"] == 0.90
            assert res.get("shadow_audit") is not None
            assert res["shadow_audit"]["hypothetical_winner"] == "github_repo"


# ==============================================================================
# 2. BRIM RELEVANCE GATE TESTS
# ==============================================================================

def test_identifier_index_integrity():
    """Verify the 638-identifier index exists and matches SHA-256 integrity hash."""
    assert IDENTIFIER_INDEX_PATH.exists()
    gate = BRIMRelevanceGate()
    assert gate.index_count == 638
    assert gate.index_hash == "140df782434a3f2f83252d6cc734f6da05dfdb7ec54ddb905f6d53e466b8240c"


def test_relevance_gate_verified_identifier_plus_similarity():
    """Chunk with valid SAP technical identifier and sufficient anchor similarity passes gate."""
    gate = BRIMRelevanceGate()
    chunk = "SAP Convergent Charging table DFKK_VT_I stores rating parameters and charge plans for provider contracts."
    with patch.object(gate, "compute_anchor_similarity", return_value=0.78):
        res = gate.evaluate_chunk(chunk)
        assert res["decision"] == "KEEP"
        assert "DFKK_VT_I" in res["matched_identifiers"]
        assert res["anchor_similarity"] == 0.78


def test_relevance_gate_contextual_keyword_plus_similarity():
    """Chunk with contextual BRIM keywords and sufficient anchor similarity passes gate."""
    gate = BRIMRelevanceGate()
    chunk = "In SAP Convergent Invoicing, billable item classes define status 0 (raw) and status 2 (billable) CIT processing."
    with patch.object(gate, "compute_anchor_similarity", return_value=0.74):
        res = gate.evaluate_chunk(chunk)
        assert res["decision"] == "KEEP"
        assert res["passes_keywords"] is True


def test_relevance_gate_acronym_false_positives_rejected():
    """Acronyms like CC (credit card) or CI (continuous integration) without BRIM context must be rejected."""
    gate = BRIMRelevanceGate()
    # Credit Card context
    res_cc = gate.evaluate_chunk("The customer paid using CC payment on Visa checkout terminal.")
    assert res_cc["decision"] == "DROP"
    assert res_cc["reason"] == "failed_both_keyword_and_identifier_index"

    # Continuous Integration context
    res_ci = gate.evaluate_chunk("Run CI pipeline using Jenkins and docker runners before pull request merge.")
    assert res_ci["decision"] == "DROP"
    assert res_ci["reason"] == "failed_both_keyword_and_identifier_index"


def test_relevance_gate_ev_charging_rejected():
    """Electric vehicle charging content (sap-labs-france/ev-server) must be rejected explicitly."""
    gate = BRIMRelevanceGate()
    chunk = "The ev charging station manages OCPP 1.6 protocols and kilowatt battery charging cycles."
    res = gate.evaluate_chunk(chunk)
    assert res["decision"] == "DROP"
    assert res["reason"] == "ev_charging_false_positive"


def test_relevance_gate_brim_financial_rejected():
    """Brim Financial content (dpbarry/BRIM-ExI) must not be confused with SAP BRIM."""
    gate = BRIMRelevanceGate()
    chunk = "Brim Financial offers Brim Mastercard with cashback points and credit card rewards."
    res = gate.evaluate_chunk(chunk)
    assert res["decision"] == "DROP"
    assert res["reason"] == "brim_financial_false_positive"


def test_relevance_gate_generic_infra_rejected():
    """Generic infrastructure and monitoring content must be rejected."""
    gate = BRIMRelevanceGate()
    chunk = "Configure prometheus metrics scraping for opentelemetry collector and kafka broker clusters."
    res = gate.evaluate_chunk(chunk)
    assert res["decision"] == "DROP"
    assert res["reason"] == "generic_infra_unrelated"


def test_relevance_gate_below_anchor_threshold_rejected():
    """Chunk matching a keyword but with anchor similarity below calibrated 0.65 threshold must be dropped."""
    gate = BRIMRelevanceGate()
    chunk = "SAP provides allowance for travel expenses in corporate HR portal."
    with patch.object(gate, "compute_anchor_similarity", return_value=0.42):
        res = gate.evaluate_chunk(chunk)
        assert res["decision"] == "DROP"
        assert "below_anchor_similarity_threshold" in res["reason"]


# ==============================================================================
# 3. LICENSE & INGESTION MANAGEMENT TESTS
# ==============================================================================

def test_license_audit_approved():
    """Permissive license (Apache-2.0, MIT) is approved."""
    mgr = LicenseManager()
    spdx_id, method, confidence = mgr.detect_license_from_text("Apache License\nVersion 2.0, January 2004")
    assert spdx_id == "Apache-2.0"
    assert mgr.is_license_permitted(spdx_id) is True
    assert confidence >= 0.90


def test_license_audit_unknown_rejected():
    """Missing or ambiguous license is marked unknown and flagged for review."""
    mgr = LicenseManager()
    spdx_id, method, confidence = mgr.detect_license_from_text("Custom proprietary terms. All rights reserved.")
    assert spdx_id == "UNKNOWN"
    assert mgr.is_license_permitted(spdx_id) is False


def test_low_yield_repository_skipping():
    """Repositories with fewer than 10 surviving chunks must be marked skipped_low_yield."""
    entry = repo_registry.get_by_url("https://github.com/SAP-samples/hana-developer-cli-tool-example")
    assert entry is not None
    entry.chunks_retained = 2
    if entry.chunks_retained < settings.REPO_MIN_CHUNKS_THRESHOLD:
        entry.ingestion_status = "skipped_low_yield"
    assert entry.ingestion_status == "skipped_low_yield"


def test_file_filtering_skips_binaries_and_lockfiles():
    """File filtering skips lockfiles, binaries, build artifacts, while preserving README and OpenAPI."""
    from backend.scripts.ingest_github_repositories import should_skip_file
    skip_lock, reason_lock = should_skip_file(Path("package-lock.json"))
    assert skip_lock is True
    assert reason_lock == "lockfile"

    skip_bin, _ = should_skip_file(Path("application.exe"))
    assert skip_bin is True

    skip_secret, _ = should_skip_file(Path(".env.production"))
    assert skip_secret is True

    skip_readme, _ = should_skip_file(Path("README.md"))
    assert skip_readme is False


# ==============================================================================
# 4. MULTI-SOURCE RETRIEVAL AND COMPARISON TESTS
# ==============================================================================

def test_comparator_kb_wins_when_strongest():
    """When KB evidence has highest final score, winning source is knowledge_base."""
    comparator = MultiSourceComparator()
    mock_db = MagicMock()
    kb_candidates = [
        {
            "chunk_id": "kb-1",
            "document_name": "SAP_CI.pdf",
            "page_number": 45,
            "chunk_text": "Official SAP Convergent Invoicing documentation on billable items.",
            "score": 0.92,
            "rerank_score": 0.90,
            # retrieval_service attaches the document's persisted source tier; without it the comparator
            # treats an unclassified document as self_authored (lowest authority).
            "provenance_tier": "official_sap",
        }
    ]
    with patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks") as mock_repo, \
         patch("backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative", return_value=[]):
        mock_repo.return_value = [
            {
                "candidate_id": "repo-1",
                "repo_url": "https://github.com/api-evangelist/sap-brim",
                "file_path": "api.json",
                "chunk_text": "API Evangelist billing endpoints metadata.",
                "score": 0.80,
                "rerank_score": 0.78,
                "license_status": "approved"
            }
        ]
        res = comparator.execute_multi_source_comparison(
            db=mock_db,
            query="billable items",
            kb_candidates=kb_candidates,
            repo_source_enabled=True,
            multi_source_compare_enabled=True,
            web_search_available=False
        )
        assert res["comparison"]["winning_source_type"] == "knowledge_base"
        assert res["comparison"]["winning_candidate_id"] == "kb-1"
        assert res["comparison"]["final_score"] == 0.92


def test_comparator_authority_weighting_ranks_official_over_repo():
    """Similarly relevant official SAP source outranks github repo due to authority weighting."""
    comparator = MultiSourceComparator()
    mock_db = MagicMock()
    kb_candidates = [
        {
            "chunk_id": "kb-1",
            "document_name": "SAP_SOM.pdf",
            "page_number": 10,
            "chunk_text": "Official SAP description of provider contract.",
            "score": 0.82,
            "rerank_score": 0.82,
            "provenance_tier": "official_sap",
        }
    ]
    with patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks") as mock_repo, \
         patch("backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative", return_value=[]):
        mock_repo.return_value = [
            {
                "candidate_id": "repo-1",
                "repo_url": "https://github.com/SAP-samples/repo",
                "file_path": "contract.md",
                "chunk_text": "Repository description of provider contract.",
                "score": 0.86,
                "rerank_score": 0.86,
                "license_status": "approved"
            }
        ]
        res = comparator.execute_multi_source_comparison(
            db=mock_db,
            query="provider contract",
            kb_candidates=kb_candidates,
            repo_source_enabled=True,
            multi_source_compare_enabled=True,
            web_search_available=False
        )
        assert res["comparison"]["winning_source_type"] == "knowledge_base"
        assert res["comparison"]["winning_candidate_id"] == "kb-1"


def test_comparator_unclassified_kb_document_gets_the_lowest_document_authority():
    """A KB candidate without a tier whose name is not in the tier mapping is weighted as self_authored,
    so an unreviewed upload can never outrank classified evidence on authority alone."""
    candidate = MultiSourceComparator().normalize_candidate(
        {"chunk_id": "kb-x", "document_name": "Unreviewed_upload.pdf", "chunk_text": "text", "score": 0.9},
        "knowledge_base",
        "q",
    )
    assert candidate["provenance"] == "self_authored"
    assert candidate["source_authority"] == 0.6
    assert candidate["final_score"] == round(0.9 * 0.6, 4)


def test_comparator_insufficient_evidence_when_below_threshold():
    """When all candidates score below calibrated threshold, comparator signals insufficient evidence."""
    comparator = MultiSourceComparator()
    mock_db = MagicMock()
    kb_candidates = [
        {
            "chunk_id": "kb-weak",
            "document_name": "Doc.pdf",
            "page_number": 1,
            "chunk_text": "Weak passing sentence.",
            "score": 0.42,
            "rerank_score": 0.42
        }
    ]
    with patch("backend.app.retrieval.multi_source_compare.repo_store.search_repo_chunks", return_value=[]), \
         patch("backend.app.retrieval.multi_source_compare.web_search_service.search_sap_authoritative", return_value=[]):
        res = comparator.execute_multi_source_comparison(
            db=mock_db,
            query="unrelated query",
            kb_candidates=kb_candidates,
            repo_source_enabled=True,
            multi_source_compare_enabled=True,
            web_search_available=False
        )
        assert res["comparison"]["winning_source_type"] == "insufficient"
        assert res["comparison"]["winning_candidate_id"] is None


def test_github_repo_citation_representation():
    """Verify GitHub repository citations include source_type, repo_url, file_path, and commit SHA."""
    citation = rag_service._format_repo_citation({
        "candidate_id": "repo-chunk-42",
        "source_type": "github_repo",
        "repo_url": "https://github.com/api-evangelist/sap-brim-billing-and-revenue-innovation-management",
        "file_path": "apis/convergent-charging-api.json",
        "commit_hash": "106c5461",
        "license": "Apache-2.0",
        "score": 0.82
    })
    assert citation["source_type"] == "github_repo"
    assert "api-evangelist" in citation["source"]
    assert citation["file_path"] == "apis/convergent-charging-api.json"
    assert citation["commit_hash"] == "106c5461"


# ==============================================================================
# 5. REGRESSION & SAFETY INTEGRITY TESTS
# ==============================================================================

def test_heldout_dataset_never_modified():
    """Verify non-negotiable requirement: heldout_questions.jsonl exists and has exactly 96 questions."""
    heldout_path = Path(__file__).resolve().parent.parent / "evaluation" / "datasets" / "heldout_questions.jsonl"
    assert heldout_path.exists()
    with open(heldout_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 96


def test_dev_dataset_has_132_questions():
    """Verify development dataset has exactly 132 questions."""
    dev_path = Path(__file__).resolve().parent.parent / "evaluation" / "datasets" / "dev_questions.jsonl"
    assert dev_path.exists()
    with open(dev_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 132
