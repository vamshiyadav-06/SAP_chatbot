"""
Observable, configurable answer confidence with explicit components.

Components are kept separate on purpose:
- retrieval_relevance:  how well retrieved passages match the question (reranker score).
                        This is NOT factual confidence.
- evidence_coverage:    share of question parts (and, for block questions, candidate
                        block types) that have at least one evidence passage.
- claim_verification:   share of material answer claims supported by evidence.
- source_authority:     authority of the passages that actually support claims.
- technical_validity:   share of technical claims (identifiers, procedures, paths)
                        without a critical validation failure. This is the runtime
                        proxy for answer correctness; true correctness against
                        reviewed references is measured by the evaluation suite.

The overall score is a weighted mean, capped whenever a critical technical claim
failed, and the publication decision is made from validation outcomes first, so a
high score can never override a failed critical claim.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from backend.app.config import settings

logger = logging.getLogger(__name__)

WEB_AUTHORITY = {
    "official_sap_help": 1.0,
    "sap_support_note": 0.95,
    "sap_learning": 0.85,
    "official_sap_other": 0.8,
    "sap_community": 0.5,
    "third_party": 0.3,
}
SUPPORTED_STATUSES = ("supported", "partially_supported")


def passage_authority(passage: Dict[str, Any]) -> float:
    """Authority weight of one passage, reusing the configured tier weights."""
    if passage.get("source_authority") is not None:
        try:
            return float(passage["source_authority"])
        except (TypeError, ValueError):
            pass
    source_type = passage.get("source_type") or ("web" if passage.get("url") else "knowledge_base")
    if source_type == "web":
        cls = passage.get("authority_class")
        if cls in WEB_AUTHORITY:
            return WEB_AUTHORITY[cls]
        domain = str(passage.get("domain") or "")
        if "help.sap.com" in domain:
            return WEB_AUTHORITY["official_sap_help"]
        if "community.sap.com" in domain or "blogs.sap.com" in domain:
            return WEB_AUTHORITY["sap_community"]
        return WEB_AUTHORITY["official_sap_other"]
    if source_type == "github_repo":
        return float(settings.TIER_WEIGHT_GITHUB_REPO)
    if source_type == "attached_document":
        return 0.6
    try:
        from backend.app.corpus.tier_definitions import DOCUMENT_TIER_MAPPING
        tier = DOCUMENT_TIER_MAPPING.get(str(passage.get("document_name") or ""), {}).get("tier", "official_sap")
    except Exception:
        tier = "official_sap"
    return {
        "official_sap": settings.TIER_WEIGHT_OFFICIAL_SAP,
        "sap_partner_or_book": settings.TIER_WEIGHT_BOOK,
        "forum": settings.TIER_WEIGHT_FORUM_WEB,
        "self_authored": settings.TIER_WEIGHT_SELF_AUTHORED,
    }.get(tier, settings.TIER_WEIGHT_OFFICIAL_SAP)


def _weights() -> Dict[str, float]:
    return {
        "retrieval_relevance": settings.CONFIDENCE_WEIGHT_RETRIEVAL,
        "evidence_coverage": settings.CONFIDENCE_WEIGHT_COVERAGE,
        "claim_verification": settings.CONFIDENCE_WEIGHT_CLAIMS,
        "source_authority": settings.CONFIDENCE_WEIGHT_AUTHORITY,
        "technical_validity": settings.CONFIDENCE_WEIGHT_TECHNICAL,
    }


def compute_components(
    *,
    retrieval_relevance: float,
    passages: Sequence[Dict[str, Any]],
    verification: Dict[str, Any],
    aspects: Optional[Sequence[Dict[str, Any]]] = None,
    scope: Optional[Any] = None,
) -> Dict[str, float]:
    citable = [p for p in passages if not (p.get("retrieval_gap") or p.get("source_type") == "retrieval_gap")]

    coverage_parts: List[float] = []
    if aspects:
        coverage_parts.append(sum(1 for a in aspects if a.get("evidence_count", 0) > 0) / len(aspects))
    else:
        coverage_parts.append(1.0 if citable else 0.0)
    if scope is not None and getattr(scope, "is_restriction_query", False) and scope.candidate_categories:
        covered = {p.get("restriction_scope") for p in citable if p.get("restriction_scope")}
        coverage_parts.append(len(covered & set(scope.candidate_categories)) / len(scope.candidate_categories))
    evidence_coverage = sum(coverage_parts) / len(coverage_parts)

    claims = verification.get("claims") or []
    material = [c for c in claims if c.get("status") not in ("qualified", "clarification")]
    supported = [c for c in material if c.get("status") in SUPPORTED_STATUSES]
    claim_verification = len(supported) / len(material) if material else 0.0

    by_id = {p.get("evidence_id"): p for p in citable if p.get("evidence_id")}
    used = [
        by_id[i] for c in supported
        for i in ([c.get("best_evidence_id")] + list(c.get("cited_evidence_ids") or [])) if i in by_id
    ]
    authority_pool = used or citable
    source_authority = sum(passage_authority(p) for p in authority_pool) / len(authority_pool) if authority_pool else 0.0

    technical_claims = [c for c in material if c.get("technical_checks")]
    critical_claims = [c for c in technical_claims if any(t.get("critical") for t in c.get("technical_checks", []))]
    technical_validity = 1.0 - (len(critical_claims) / len(technical_claims)) if technical_claims else 1.0
    if verification.get("critical_failures") and not technical_claims:
        technical_validity = 0.0

    return {
        "retrieval_relevance": round(max(0.0, min(1.0, float(retrieval_relevance or 0.0))), 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "claim_verification": round(claim_verification, 4),
        "source_authority": round(source_authority, 4),
        "technical_validity": round(technical_validity, 4),
    }


def decide(verification: Dict[str, Any], *, repaired: bool, guard_applied: bool = False) -> Dict[str, Any]:
    """Publication decision from validation outcomes (not from the weighted score)."""
    claims = verification.get("claims") or []
    supported = [c for c in claims if c.get("status") in SUPPORTED_STATUSES]
    critical = verification.get("critical_failures") or []
    reasons: List[str] = []
    if verification.get("passes_grounding_gate") and not critical and not guard_applied:
        decision = "repaired" if repaired else "accepted"
        reasons.append("All publication-gate conditions met" + (" after one repair." if repaired else "."))
    elif supported:
        decision = "partial"
        if guard_applied:
            reasons.append("Claims that failed critical validation were removed and the unresolved points are stated.")
        if critical:
            reasons.append(f"{len(critical)} critical technical claim(s) failed validation.")
        if verification.get("unsupported_claims"):
            reasons.append(f"{len(verification['unsupported_claims'])} claim(s) unsupported by the selected evidence.")
        if not reasons:
            reasons.append(
                f"Grounding score {verification.get('grounding_score')} below threshold {settings.ANSWER_GROUNDING_THRESHOLD}."
            )
    else:
        decision = "rejected"
        reasons.append("No material claim is supported by the selected evidence.")
    return {"decision": decision, "reasons": reasons}


def build_report(
    *,
    retrieval_relevance: float,
    passages: Sequence[Dict[str, Any]],
    verification: Dict[str, Any],
    aspects: Optional[Sequence[Dict[str, Any]]] = None,
    scope: Optional[Any] = None,
    repair: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    components = compute_components(
        retrieval_relevance=retrieval_relevance, passages=passages, verification=verification,
        aspects=aspects, scope=scope,
    )
    weights = _weights()
    total_weight = sum(weights.values()) or 1.0
    overall = sum(components[k] * weights[k] for k in components) / total_weight
    critical = verification.get("critical_failures") or []
    cap = float(settings.CRITICAL_FAILURE_CONFIDENCE_CAP)
    capped = bool(critical) and overall > cap
    if critical:
        overall = min(overall, cap)
    repair = dict(repair or {})
    decision = decide(verification, repaired=bool(repair.get("adopted")), guard_applied=bool(repair.get("guard_applied")))

    claims = verification.get("claims") or []
    return {
        "decision": decision["decision"],
        "decision_reasons": decision["reasons"],
        "overall_confidence": round(overall, 4),
        "overall_capped_by_critical_failure": capped,
        "components": components,
        "weights": weights,
        "thresholds": {
            "answer_grounding": settings.ANSWER_GROUNDING_THRESHOLD,
            "internal_evidence": settings.INTERNAL_EVIDENCE_THRESHOLD,
            "document_match": settings.DOCUMENT_MATCH_THRESHOLD,
            "critical_failure_cap": cap,
        },
        "grounding_score": verification.get("grounding_score"),
        "verification_status": verification.get("verification_status"),
        "passes_grounding_gate": verification.get("passes_grounding_gate"),
        "claim_counts": {
            status: sum(1 for c in claims if c.get("status") == status)
            for status in sorted({str(c.get("status")) for c in claims})
        },
        "critical_failures": [
            {k: (v[:300] if isinstance(v, str) else v) for k, v in f.items()} for f in critical
        ],
        "citation_checks": verification.get("citation_checks"),
        "evidence_conflicts": verification.get("evidence_conflicts", []),
        "restriction_scope": scope.to_dict() if scope is not None and hasattr(scope, "to_dict") else None,
        "repair": repair,
        "evidence": [
            {
                "id": p.get("evidence_id"),
                "source_type": p.get("source_type"),
                "document": p.get("document_name") or p.get("title"),
                "url": p.get("url"),
                "authority": round(passage_authority(p), 3),
                "authority_class": p.get("authority_class"),
                "release": p.get("release"),
                "restriction_scope": p.get("restriction_scope"),
            }
            for p in passages if p.get("evidence_id")
        ],
    }


def log_report(report: Dict[str, Any], query: str) -> None:
    """Structured server-side audit line (never sent to ordinary users)."""
    logger.info(
        "answer_validation decision=%s overall=%.3f gate=%s critical=%d components=%s query=%r",
        report.get("decision"), report.get("overall_confidence", 0.0), report.get("passes_grounding_gate"),
        len(report.get("critical_failures") or []), report.get("components"), (query or "")[:120],
    )
