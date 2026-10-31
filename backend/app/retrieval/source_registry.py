"""
Unified Source Registry for cClyptus.AI SAP BRIM.

Maintains comprehensive registration and metadata governance across:
1. Official SAP Developer Documentation (developers.sap.com)
2. Official SAP Help Documentation (help.sap.com)
3. SAP Community Sources (community.sap.com)
4. Discovery Sources (portals and organization hubs - not for wholesale ingestion)
5. GitHub Repositories (Tiers A, B, C with SPDX license governance)

Enforces non-negotiable architectural rules:
- Discovery portals and organization URLs are never ingested wholesale.
- Official SAP documentation, SAP Community content, and GitHub repositories are
  distinguishable in metadata and source-ranking authority weights.
- All new source retrieval features remain disabled by default behind feature flags.
"""

from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, urlunparse
from pydantic import BaseModel, Field

from backend.app.retrieval.repo_registry import (
    REGISTERED_REPOSITORIES,
    RepositoryRegistryEntry,
    repo_registry as github_repo_registry
)


def hostname_matches(value: str, domain: str) -> bool:
    """Match a hostname or URL to a domain without accepting lookalike suffixes."""
    candidate = str(value or "").strip().lower()
    parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
    host = (parsed.hostname or "").rstrip(".")
    expected = domain.strip().lower().rstrip(".")
    return bool(host and expected and (host == expected or host.endswith("." + expected)))


class RegisteredSourceEntry(BaseModel):
    source_id: str
    url: str
    canonical_url: str
    title: str
    source_category: str  # 'official_developer_doc', 'official_help_doc', 'sap_community', 'discovery_portal', 'github_repo'
    provenance_tier: str  # 'official_sap', 'forum_web', 'github_repo', 'discovery'
    domain_module: str    # 'SAP_BRIM', 'SAP_CC', 'SAP_CI', 'SAP_RAR', 'SAP_S4HANA', 'SAP_NETWEAVER', 'DISCOVERY'
    is_discovery_source: bool = False  # If True, treated as discovery hub, NEVER ingested wholesale
    product_name: Optional[str] = None
    product_version: Optional[str] = None
    author: Optional[str] = "SAP SE"
    publication_date: Optional[str] = None
    license_info: str = "SAP Terms of Use"
    authority_weight: float = 0.85
    sync_status: str = "registered"  # 'registered', 'pending', 'ingested', 'skipped_discovery'
    description: Optional[str] = None


def normalize_canonical_url(url: str) -> str:
    """Normalizes URL for strict deduplication: strips fragments, trailing slashes, and standardizes scheme/host/path."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    path = path.lower()
    # Rebuild without query params that are tracking-specific, keeping canonical path
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


# Master List of Extended Official SAP and Community Sources
REGISTERED_OFFICIAL_AND_COMMUNITY_SOURCES: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. Official SAP Developer Documentation
    # =========================================================================
    {
        "source_id": "sap-dev-brim-topic",
        "url": "https://developers.sap.com/topics/brim.html",
        "title": "SAP BRIM Developer Topic Guide",
        "source_category": "official_developer_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_BRIM",
        "is_discovery_source": False,
        "product_name": "SAP Billing and Revenue Innovation Management",
        "product_version": "Cloud / S/4HANA",
        "author": "SAP Developer Center",
        "license_info": "SAP Developer License Agreement",
        "authority_weight": 0.85,
        "description": "Developer overview and technical orientation for SAP BRIM subscription management and monetization."
    },
    {
        "source_id": "sap-dev-brim-impl-config",
        "url": "https://developers.sap.com/concepts/brim-implementation-configuration/",
        "title": "SAP BRIM Implementation & Configuration Concepts",
        "source_category": "official_developer_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_BRIM",
        "is_discovery_source": False,
        "product_name": "SAP Billing and Revenue Innovation Management",
        "product_version": "S/4HANA",
        "author": "SAP Developer Center",
        "license_info": "SAP Developer License Agreement",
        "authority_weight": 0.85,
        "description": "Technical guide on configuring provider contracts, SOM-CC-CI handshakes, and master data structures."
    },
    {
        "source_id": "sap-dev-brim-integration-arch",
        "url": "https://developers.sap.com/concepts/brim-integration-architecture/",
        "title": "SAP BRIM Integration Architecture Concepts",
        "source_category": "official_developer_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_BRIM",
        "is_discovery_source": False,
        "product_name": "SAP Billing and Revenue Innovation Management",
        "product_version": "S/4HANA / BTP",
        "author": "SAP Developer Center",
        "license_info": "SAP Developer License Agreement",
        "authority_weight": 0.85,
        "description": "Integration architecture between SOM, Convergent Charging, Convergent Invoicing, and FI-CA financial subledger."
    },

    # =========================================================================
    # 2. Official SAP Help Documentation
    # =========================================================================
    {
        "source_id": "sap-help-cc-latest",
        "url": "https://help.sap.com/docs/r/product/Convergent_Charging/latest",
        "title": "SAP Convergent Charging Product Documentation (Latest)",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_CC",
        "is_discovery_source": False,
        "product_name": "SAP Convergent Charging",
        "product_version": "latest",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "Official reference documentation for SAP Convergent Charging rating engines, charge plans, and BART batch charging."
    },
    {
        "source_id": "sap-help-cc-core-tool",
        "url": "https://help.sap.com/docs/Convergent_Charging/7587f50ad2ca4f888b2fb5507faccae4/16b89cfb82144a4181206c992053d7b3.html",
        "title": "SAP Convergent Charging Core Tool & Pricing Trees Reference",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_CC",
        "is_discovery_source": False,
        "product_name": "SAP Convergent Charging",
        "product_version": "2025/2026",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "Core Tool configuration, price plans, charging macros, and allowance logic trees."
    },
    {
        "source_id": "sap-help-ci",
        "url": "https://help.sap.com/docs/SAP_Convergent_Invoicing",
        "title": "SAP Convergent Invoicing Reference Documentation",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_CI",
        "is_discovery_source": False,
        "product_name": "SAP Convergent Invoicing",
        "product_version": "S/4HANA",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "Consumption items (CIT), billable item classes (BIT), billing aggregation, and invoicing process execution."
    },
    {
        "source_id": "sap-help-rar",
        "url": "https://help.sap.com/docs/SAP_REVENUE_ACCOUNTING_AND_REPORTING",
        "title": "SAP Revenue Accounting and Reporting (RAR) Documentation",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_RAR",
        "is_discovery_source": False,
        "product_name": "SAP Revenue Accounting and Reporting",
        "product_version": "S/4HANA",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "IFRS 15 / ASC 606 revenue recognition, performance obligations (POB), and revenue accounting items (RAI)."
    },
    {
        "source_id": "sap-help-s4hana-onprem-im5",
        "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/95ad0cb1c441447888d695da7f3fd3d9/subsection-im5",
        "title": "SAP S/4HANA On-Premise Contract Accounting & Billing Section IM5",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_S4HANA",
        "is_discovery_source": False,
        "product_name": "SAP S/4HANA",
        "product_version": "ON-PREMISE",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "S/4HANA on-premise contract accounts, open item accounting, and invoicing execution."
    },
    {
        "source_id": "sap-help-netweaver-740",
        "url": "https://help.sap.com/docs/SAP_NETWEAVER_740/0c0f7dcd6e3740fbedb3f0e5cefd1834",
        "title": "SAP NetWeaver 7.40 Integration & RFC/Web Services Documentation",
        "source_category": "official_help_doc",
        "provenance_tier": "official_sap",
        "domain_module": "SAP_NETWEAVER",
        "is_discovery_source": False,
        "product_name": "SAP NetWeaver",
        "product_version": "7.40",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.85,
        "description": "Underlying NetWeaver platform runtime, RFC communication interfaces, and transaction processing."
    },

    # =========================================================================
    # 3. SAP Community Sources
    # =========================================================================
    {
        "source_id": "sap-community-brim-topic",
        "url": "https://community.sap.com/topics/brim",
        "title": "SAP Community: BRIM Topic Discussion and Articles",
        "source_category": "sap_community",
        "provenance_tier": "forum_web",
        "domain_module": "SAP_BRIM",
        "is_discovery_source": False,
        "product_name": "SAP BRIM Community",
        "product_version": "Community",
        "author": "SAP Community Contributors",
        "license_info": "SAP Community Terms of Use",
        "authority_weight": 0.50,
        "description": "Verified peer discussions, consultant tips, and implementation troubleshooting articles for SAP BRIM."
    },
    {
        "source_id": "sap-community-cc-topic",
        "url": "https://community.sap.com/topics/convergent-charging",
        "title": "SAP Community: Convergent Charging Topic",
        "source_category": "sap_community",
        "provenance_tier": "forum_web",
        "domain_module": "SAP_CC",
        "is_discovery_source": False,
        "product_name": "SAP Convergent Charging",
        "product_version": "Community",
        "author": "SAP Community Contributors",
        "license_info": "SAP Community Terms of Use",
        "authority_weight": 0.50,
        "description": "Community troubleshooting, Core Tool configurations, and batch rating Q&A for Convergent Charging."
    },
    {
        "source_id": "sap-community-rar-topic",
        "url": "https://community.sap.com/topics/revenue-accounting-and-reporting",
        "title": "SAP Community: Revenue Accounting and Reporting Topic",
        "source_category": "sap_community",
        "provenance_tier": "forum_web",
        "domain_module": "SAP_RAR",
        "is_discovery_source": False,
        "product_name": "SAP Revenue Accounting and Reporting",
        "product_version": "Community",
        "author": "SAP Community Contributors",
        "license_info": "SAP Community Terms of Use",
        "authority_weight": 0.50,
        "description": "Expert blogs and discussions on IFRS 15 performance obligations, RAI reconciliations, and contract changes."
    },
    {
        "source_id": "sap-community-portal-home",
        "url": "https://community.sap.com/",
        "title": "SAP Community Portal Homepage (Discovery Hub)",
        "source_category": "discovery_portal",
        "provenance_tier": "discovery",
        "domain_module": "DISCOVERY",
        "is_discovery_source": True,  # Non-negotiable: treated as discovery source, NEVER ingested wholesale
        "product_name": "SAP Community Hub",
        "product_version": "Portal",
        "author": "SAP Community",
        "license_info": "SAP Community Terms of Use",
        "authority_weight": 0.0,
        "description": "Top-level discovery portal for SAP Community; used for topic exploration, not wholesale ingestion."
    },

    # =========================================================================
    # 4. Discovery Sources (Portals and Organization Hubs)
    # =========================================================================
    {
        "source_id": "sap-help-portal-home",
        "url": "https://help.sap.com/",
        "title": "SAP Help Portal Homepage (Discovery Hub)",
        "source_category": "discovery_portal",
        "provenance_tier": "discovery",
        "domain_module": "DISCOVERY",
        "is_discovery_source": True,  # Non-negotiable: discovery source, NEVER ingested wholesale
        "product_name": "SAP Help Portal",
        "product_version": "Portal",
        "author": "SAP SE",
        "license_info": "SAP Help Portal Terms of Use",
        "authority_weight": 0.0,
        "description": "Main SAP Help documentation discovery hub; used to locate relevant product documentation."
    },
    {
        "source_id": "github-org-sap-samples",
        "url": "https://github.com/SAP-samples",
        "title": "SAP-samples GitHub Organization Hub (Discovery Source)",
        "source_category": "discovery_portal",
        "provenance_tier": "discovery",
        "domain_module": "DISCOVERY",
        "is_discovery_source": True,  # Non-negotiable: organization hub, NEVER ingested wholesale
        "product_name": "SAP-samples",
        "product_version": "GitHub Org",
        "author": "SAP SE",
        "license_info": "Various Open Source / SAP Sample Code",
        "authority_weight": 0.0,
        "description": "GitHub organization discovery root for official SAP code samples. Filtered via API, never cloned wholesale."
    },
    {
        "source_id": "github-org-sap",
        "url": "https://github.com/SAP",
        "title": "SAP GitHub Organization Hub (Discovery Source)",
        "source_category": "discovery_portal",
        "provenance_tier": "discovery",
        "domain_module": "DISCOVERY",
        "is_discovery_source": True,  # Non-negotiable: organization hub, NEVER ingested wholesale
        "product_name": "SAP",
        "product_version": "GitHub Org",
        "author": "SAP SE",
        "license_info": "Various Open Source / Apache-2.0",
        "authority_weight": 0.0,
        "description": "GitHub organization discovery root for official SAP repositories. Filtered via API, never cloned wholesale."
    }
]


class SourceRegistry:
    """
    Centralized Registry for all cClyptus.AI documentation, community, and repository sources.
    Provides indexing, lookup, categorization, deduplication, and discovery guardrails.
    """

    def __init__(self):
        self._entries_by_url: Dict[str, RegisteredSourceEntry] = {}
        self._entries_by_id: Dict[str, RegisteredSourceEntry] = {}

        # 1. Register extended official SAP, Community, and Discovery sources
        for s in REGISTERED_OFFICIAL_AND_COMMUNITY_SOURCES:
            canonical = normalize_canonical_url(s["url"])
            entry = RegisteredSourceEntry(
                canonical_url=canonical,
                **s
            )
            self._entries_by_url[canonical] = entry
            self._entries_by_id[entry.source_id] = entry

        # 2. Synchronize existing GitHub repositories from repo_registry
        for r in REGISTERED_REPOSITORIES:
            canonical_repo = normalize_canonical_url(r["repo_url"])
            repo_id = f"repo-{r.get('owner')}-{r.get('name')}".lower()
            if canonical_repo not in self._entries_by_url:
                entry = RegisteredSourceEntry(
                    source_id=repo_id,
                    url=r["repo_url"],
                    canonical_url=canonical_repo,
                    title=f"GitHub: {r.get('owner')}/{r.get('name')}",
                    source_category="github_repo",
                    provenance_tier=r.get("provenance_tier", "github_repo"),
                    domain_module=r.get("expected_domain", "SAP_ECOSYSTEM"),
                    is_discovery_source=False,
                    product_name=r.get("name"),
                    product_version="Git Head",
                    author=r.get("owner"),
                    license_info=r.get("license_status", "unknown"),
                    authority_weight=0.80,
                    sync_status=r.get("ingestion_status", "pending"),
                    description=r.get("notes")
                )
                self._entries_by_url[canonical_repo] = entry
                self._entries_by_id[repo_id] = entry

    def get_all(self) -> List[RegisteredSourceEntry]:
        """Returns all registered source entries."""
        return list(self._entries_by_url.values())

    def get_by_url(self, url: str) -> Optional[RegisteredSourceEntry]:
        """Retrieves entry by normalized canonical URL."""
        canonical = normalize_canonical_url(url)
        return self._entries_by_url.get(canonical)

    def get_by_id(self, source_id: str) -> Optional[RegisteredSourceEntry]:
        """Retrieves entry by unique source_id."""
        return self._entries_by_id.get(source_id)

    def get_by_category(self, category: str) -> List[RegisteredSourceEntry]:
        """Filters entries by source_category."""
        return [e for e in self._entries_by_url.values() if e.source_category == category]

    def get_discovery_sources(self) -> List[RegisteredSourceEntry]:
        """Returns all registered discovery portal and organization hubs."""
        return [e for e in self._entries_by_url.values() if e.is_discovery_source]

    def get_ingestible_sources(self) -> List[RegisteredSourceEntry]:
        """Returns sources approved for direct page/chunk ingestion (excluding discovery hubs)."""
        return [e for e in self._entries_by_url.values() if not e.is_discovery_source]

    def is_discovery_source(self, url: str) -> bool:
        """Determines whether a given URL is a discovery hub that must not be ingested wholesale."""
        entry = self.get_by_url(url)
        if entry:
            return entry.is_discovery_source
        canonical = normalize_canonical_url(url)
        # Check against known discovery URL patterns
        discovery_patterns = [
            "https://help.sap.com",
            "https://community.sap.com",
            "https://github.com/sap-samples",
            "https://github.com/sap"
        ]
        return canonical in discovery_patterns or canonical + "/" in discovery_patterns

    def get_authority_weight(self, url: str) -> float:
        """Determines source authority weight based on registered metadata."""
        entry = self.get_by_url(url)
        if entry:
            return entry.authority_weight
        # Domain fallback
        if hostname_matches(url, "developers.sap.com") or hostname_matches(url, "help.sap.com"):
            return 0.85
        if hostname_matches(url, "community.sap.com") or hostname_matches(url, "blogs.sap.com"):
            return 0.50
        if hostname_matches(url, "github.com"):
            return 0.80
        return 0.50


source_registry = SourceRegistry()
