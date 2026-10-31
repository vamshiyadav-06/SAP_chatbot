"""
Unit and Integration Tests for Source Registry, Discovery Guardrails,
and Extended Official SAP & Community Sources.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.retrieval.source_registry import (
    source_registry,
    normalize_canonical_url,
    RegisteredSourceEntry
)
from backend.app.retrieval.repo_registry import repo_registry, REGISTERED_REPOSITORIES
from backend.app.retrieval.sap_web_doc_ingest import (
    sap_web_doc_ingest_service,
    StructuredTextHTMLParser
)
from backend.app.retrieval.multi_source_compare import multi_source_comparator
from backend.app.services.confidence_scoring import passage_authority, WEB_AUTHORITY
from backend.app.services.context_packing_service import context_packing_service


# ==============================================================================
# 1. SOURCE REGISTRY COMPLETENESS TESTS
# ==============================================================================

def test_official_developer_documentation_registered():
    """Verify all requested Official SAP Developer Documentation URLs are registered."""
    expected_dev_urls = [
        "https://developers.sap.com/topics/brim.html",
        "https://developers.sap.com/concepts/brim-implementation-configuration/",
        "https://developers.sap.com/concepts/brim-integration-architecture/"
    ]
    for url in expected_dev_urls:
        entry = source_registry.get_by_url(url)
        assert entry is not None, f"Missing registered entry for {url}"
        assert entry.source_category == "official_developer_doc"
        assert entry.provenance_tier == "official_sap"
        assert entry.is_discovery_source is False
        assert entry.authority_weight == 0.85


def test_official_help_documentation_registered():
    """Verify all requested Official SAP Help Documentation URLs are registered."""
    expected_help_urls = [
        "https://help.sap.com/docs/r/product/Convergent_Charging/latest",
        "https://help.sap.com/docs/Convergent_Charging/7587f50ad2ca4f888b2fb5507faccae4/16b89cfb82144a4181206c992053d7b3.html",
        "https://help.sap.com/docs/SAP_Convergent_Invoicing",
        "https://help.sap.com/docs/SAP_REVENUE_ACCOUNTING_AND_REPORTING",
        "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/95ad0cb1c441447888d695da7f3fd3d9/subsection-im5",
        "https://help.sap.com/docs/SAP_NETWEAVER_740/0c0f7dcd6e3740fbedb3f0e5cefd1834"
    ]
    for url in expected_help_urls:
        entry = source_registry.get_by_url(url)
        assert entry is not None, f"Missing registered entry for {url}"
        assert entry.source_category == "official_help_doc"
        assert entry.provenance_tier == "official_sap"
        assert entry.is_discovery_source is False
        assert entry.authority_weight == 0.85


def test_sap_community_sources_registered():
    """Verify all requested SAP Community topic URLs are registered."""
    expected_community_topics = [
        "https://community.sap.com/topics/brim",
        "https://community.sap.com/topics/convergent-charging",
        "https://community.sap.com/topics/revenue-accounting-and-reporting"
    ]
    for url in expected_community_topics:
        entry = source_registry.get_by_url(url)
        assert entry is not None, f"Missing registered entry for {url}"
        assert entry.source_category == "sap_community"
        assert entry.provenance_tier == "forum_web"
        assert entry.is_discovery_source is False
        assert entry.authority_weight == 0.50


def test_discovery_sources_properly_flagged():
    """Verify portals and organization URLs are registered strictly as discovery sources."""
    discovery_urls = [
        "https://help.sap.com/",
        "https://community.sap.com/",
        "https://github.com/SAP-samples",
        "https://github.com/SAP"
    ]
    for url in discovery_urls:
        entry = source_registry.get_by_url(url)
        assert entry is not None, f"Missing discovery entry for {url}"
        assert entry.is_discovery_source is True, f"{url} MUST be flagged as discovery source"
        assert entry.provenance_tier == "discovery"
        assert source_registry.is_discovery_source(url) is True


def test_existing_github_repos_preserved():
    """Verify all existing GitHub repositories remain registered with intact metadata."""
    assert len(REGISTERED_REPOSITORIES) >= 15
    for r in REGISTERED_REPOSITORIES:
        repo_url = r["repo_url"]
        # Check in repo_registry
        repo_entry = repo_registry.get_by_url(repo_url)
        assert repo_entry is not None, f"Repo {repo_url} missing in repo_registry"
        assert repo_entry.tier == r["tier"]

        # Check in unified source_registry
        source_entry = source_registry.get_by_url(repo_url)
        assert source_entry is not None, f"Repo {repo_url} missing in source_registry"
        assert source_entry.source_category == "github_repo"


# ==============================================================================
# 2. DISCOVERY SOURCE GUARDRAIL & WHOLESALE INGESTION PREVENTION
# ==============================================================================

def test_discovery_sources_prevented_from_wholesale_ingestion():
    """Discovery sources must be rejected from wholesale ingestion."""
    discovery_entries = source_registry.get_discovery_sources()
    assert len(discovery_entries) >= 4

    for entry in discovery_entries:
        res = sap_web_doc_ingest_service.process_registered_source(entry)
        assert res["status"] == "skipped_discovery_source"
        assert res["chunks_count"] == 0
        assert "wholesale" in res["reason"].lower()


# ==============================================================================
# 3. CANONICAL URL & CONTENT DEDUPLICATION TESTS
# ==============================================================================

def test_canonical_url_normalization():
    """Verify URL normalization strips fragments and standardizes paths."""
    url1 = "https://developers.sap.com/topics/brim.html/"
    url2 = "https://developers.sap.com/topics/brim.html"
    assert normalize_canonical_url(url1) == normalize_canonical_url(url2)

    url_with_fragment = "https://help.sap.com/docs/SAP_Convergent_Invoicing#section-1"
    assert normalize_canonical_url(url_with_fragment) == "https://help.sap.com/docs/sap_convergent_invoicing"


def test_duplicate_url_skipped_during_ingestion():
    """Repeated URLs within an ingestion run must be detected and deduplicated."""
    service = sap_web_doc_ingest_service
    test_entry = source_registry.get_by_url("https://developers.sap.com/topics/brim.html")
    assert test_entry is not None

    mock_html = "<html><head><title>SAP BRIM</title></head><body><h1>SAP BRIM</h1><p>Test paragraph content for BRIM.</p></body></html>"
    # First run processes
    service._seen_canonical_urls.clear()
    res1 = service.process_registered_source(test_entry, mock_html=mock_html)
    assert res1["status"] == "ingested_successfully"

    # Second run with same canonical URL must be skipped
    res2 = service.process_registered_source(test_entry, mock_html=mock_html)
    assert res2["status"] == "skipped_duplicate_url"


def test_overlapping_content_hash_deduplication():
    """Duplicate text blocks across sections or calls must be deduplicated by SHA-256."""
    service = sap_web_doc_ingest_service
    service._seen_content_hashes.clear()

    extracted_data = {
        "source_id": "test-1",
        "canonical_url": "https://example.com/test",
        "source_category": "official_developer_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_BRIM",
        "title": "Title",
        "product_name": "BRIM",
        "product_version": "2026",
        "author": "SAP",
        "publication_date": "2026-01-01",
        "authority_weight": 0.85,
        "sections": [
            {"heading": "Sec1", "text": "This is a detailed paragraph about SAP Convergent Charging rating logic and BART processing."},
            {"heading": "Sec2", "text": "This is a detailed paragraph about SAP Convergent Charging rating logic and BART processing."}  # Duplicate!
        ]
    }
    chunks = service.chunk_extracted_data(extracted_data)
    # The duplicate block should be filtered out
    assert len(chunks) == 1
    assert chunks[0]["heading"] == "Sec1"


# ==============================================================================
# 4. SOURCE DISTINGUISHABILITY & AUTHORITY WEIGHT TESTS
# ==============================================================================

def test_authority_ranking_distinguishes_official_vs_community():
    """Official SAP documentation and SAP Community must have distinct authority weights."""
    comparator = multi_source_comparator

    # Official developer doc
    dev_weight = comparator.get_source_authority_weight(
        provenance_tier="official_sap",
        domain="developers.sap.com"
    )
    # Official help doc
    help_weight = comparator.get_source_authority_weight(
        provenance_tier="official_sap",
        domain="help.sap.com"
    )
    # SAP Community forum
    community_weight = comparator.get_source_authority_weight(
        provenance_tier="forum_web",
        domain="community.sap.com"
    )
    # GitHub repository
    repo_weight = comparator.get_source_authority_weight(
        provenance_tier="github_repo",
        domain="github.com"
    )

    assert dev_weight == 0.85
    assert help_weight == 0.85
    assert repo_weight == 0.80
    assert community_weight == 0.50

    # Non-negotiable rule: Official SAP doc must strictly outrank Community content
    assert dev_weight > community_weight
    assert help_weight > community_weight
    assert repo_weight > community_weight


def test_authority_domain_matching_rejects_lookalike_hostnames():
    comparator = multi_source_comparator
    assert comparator.get_source_authority_weight("unknown", "help.sap.com.evil.tld") == 0.50
    assert comparator.get_source_authority_weight("unknown", "sub.help.sap.com") == 0.85
    assert source_registry.get_authority_weight("https://help.sap.com.evil.tld/doc") == 0.50
    assert source_registry.get_authority_weight("https://sub.help.sap.com/doc") == 0.85
    assert passage_authority({"source_type": "web", "domain": "help.sap.com.evil.tld"}) == WEB_AUTHORITY["official_sap_other"]
    assert context_packing_service.infer_chunk_tier({
        "source_type": "web", "url": "https://help.sap.com.evil.tld/doc"
    }) == "forum"


# ==============================================================================
# 5. FEATURE FLAG DEFAULT SAFETY TEST
# ==============================================================================

def test_web_sources_feature_flag_defaults_to_false():
    """Verify non-negotiable requirement: new web sources feature flag defaults to False."""
    assert settings.SAP_WEB_SOURCES_ENABLED is False
    assert settings.REPO_SOURCE_ENABLED is False
    assert settings.MULTI_SOURCE_COMPARE_ENABLED is False
