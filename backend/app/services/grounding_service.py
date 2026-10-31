import re
import logging
from typing import List, Dict, Any, Tuple, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)

# SAP technical patterns for strict verification (only real SAP transactions and tables)
from backend.app.services.sap_entity_service import sap_entity_service
from backend.app.services.sap_identifier_validator import (
    sap_identifier_validator,
    NON_FAILING_STATUSES,
    content_terms,
    passage_text,
    is_gap,
    release_context,
)
from backend.app.services.evidence_markers import MARKER_PATTERN, extract_marker_ids, assign_evidence_ids

# Causal/effect connectors: both sides of the relationship must be supported by one passage.
CAUSAL_CONNECTOR = re.compile(
    r"\b(because|therefore|hence|consequently|as\s+a\s+result|results?\s+in|leads?\s+to|caus(?:es|ed|ing)|"
    r"due\s+to|so\s+that|which\s+means|triggers?|will\s+automatically|automatically)\b",
    re.IGNORECASE,
)
# Evidence sentence that itself expresses causation/consequence.
EVIDENCE_CAUSAL_MARKER = re.compile(
    r"\b(because|therefore|hence|thus|consequently|as\s+a\s+result|results?\s+in|leads?\s+to|caus\w+|due\s+to|"
    r"so\s+that|which\s+means|triggers?|automatically|prevents?|ensures?|if|when|once|after)\b",
    re.IGNORECASE,
)
# Effects attributed to a maintenance action ("removing the block will release ...").
PROCEDURE_EFFECT = re.compile(
    r"\b(remov\w+|unblock\w*|unlock\w*|releas\w+|delet\w+|reset\w*|lift\w*|clear\w*)\b.*"
    r"\b(will|would|automatically|immediately|allows?|enables?|causes?|results?|triggers?|lets?)\b",
    re.IGNORECASE,
)

# High-precision SAP technical patterns for strict verification
TCODE_PATTERN = re.compile(
    r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|fkkbix_[a-z0-9_]+|fkkbi_[a-z0-9_]+|fkk[a-z0-9_]+|"
    r"fp[a-z0-9_]{2,8}|crmd_[a-z0-9_]+|farr_[a-z0-9_]+|wty_[a-z0-9_]+|"
    r"me[0-9]{2}[a-z]?|va[0-9]{2}|vf[0-9]{2}|vk[0-9]{2}|fb[0-9]{2}|f110|"
    r"se[0-9]{2}[a-z]?|sm[0-9]{2}|st[0-9]{2}|slg[0-9]|spro|swo1|sicf|miro|migo)\b",
    re.IGNORECASE
)
TABLE_PATTERN = re.compile(
    r"\b(dfkk[a-z0-9_]+|erdk|erch|but0[0-9]{2}|but0bk|mara|marc|vbak|vbap|ekko|ekpo|bseg|bkpf|v_fkk[a-z0-9_]+)\b",
    re.IGNORECASE
)
SPRO_PATTERN = re.compile(
    r"\b(spro|img\s+path|customizing\s+path|sap\s+customizing\s+implementation\s+guide)\b",
    re.IGNORECASE
)

# Non-TCode words and acronyms to ignore so they aren't false-positived as technical identifiers
EXCLUDED_TECH_TOKENS = {
    "b2b", "b2c", "p10", "p50", "p90", "p95", "p99", "v1", "v2", "v3", "ed1",
    "2nd", "1st", "3rd", "sap", "som", "cc", "ci", "fica", "rar", "crm", "ecc",
    "gui", "iot", "api", "erp", "rfc", "tcp", "ssl", "http", "rest", "soap",
    "json", "xml", "csv", "sql", "hana", "btp", "cdr", "bit", "cit", "sla",
    "e2e", "q1", "q2", "q3", "q4", "24x7", "2020", "1909", "404", "500", "100",
    "http400", "http500", "http200"
}

STOP_WORDS = {
    "what", "is", "the", "a", "an", "how", "to", "in", "of", "and", "for", "with",
    "does", "do", "explain", "can", "you", "tell", "me", "about", "this", "that", "these",
    "those", "are", "from", "into", "onto", "upon", "which", "there", "their", "they",
    "here", "based", "according", "following", "overview", "summary", "functions",
    "also", "used", "been", "have", "has", "will", "would", "could", "should", "process",
    "system", "between", "during", "before", "after", "through", "ensures", "ensuring"
}

# Comprehensive registry of standard SAP BRIM & S/4HANA objects
VERIFIED_STANDARD_SAP_OBJECTS = {
    # CI Transactions & Tables
    "spro", "fkkbi_class", "fkkbix_class", "fkkbix_conf", "fkkbix_bit_mon", "fkkbix_cit_mon",
    "fkkbix_rate", "fkkbix_bill", "fkkbix_inv", "fkkbix_bit_disp", "fkkbix",
    "fkkbix_bill_m", "fkkbix_inv_m",
    "dfkkbixbit0", "dfkkbixbit1", "dfkkbixbit2", "dfkkbixbit3", "dfkkbixbit4",
    "dfkkbixcit0", "dfkkbixcit1", "dfkkbixcit2", "dfkkbixcit3", "dfkkbixcit4",
    "dfkkbict", "dfkkbict_it", "dfkkbict_py", "dfkkbict_tx", "dfkkinv_ord", "dfkkinv_doc",
    "dfkkinvdoc", "dfkkinvdoc_h", "dfkkinvdoc_i", "dfkkinvdoc_p",
    "dfkkbilldoc", "dfkkbilldoc_h", "dfkkbilldoc_i",

    # FI-CA Transactions & Tables
    "fpc0", "fpc1", "fpc2", "fpc3", "fpl9", "fpma", "fprel", "fpva", "fpvb",
    "fpcopara", "fpci", "fpg1", "fpg4", "fp05", "fp08", "fp30", "fp40",
    "fpe1", "fpe2", "fpe3", "dfkkko", "dfkkop", "dfkkopk", "dfkklocks", "dfkkco",
    "dfkkcoll", "dfkkdumi", "fkkvk", "fkkvkp", "erdk", "erch",

    # SOM, RAR & S/4HANA
    "crmd_order", "com_product", "wty_claim", "farr_rai_mon",
    "slg1", "sm30", "sm37", "sm59", "se16", "se16n", "se38", "se80", "sicf", "swo1",
    "st05", "st22", "we02", "we20", "f110",

    # ERP Standard
    "me21n", "me22n", "me23n", "me21", "me22", "me23",
    "va01", "va02", "va03", "vf01", "vf02", "vf03", "fb01", "fb02", "fb03", "fb05",
    "migo", "miro", "ekko", "ekpo", "bseg", "bkpf", "mara", "marc", "vbak", "vbap",
    "but000", "but020", "but050", "but051", "but0bk"
}


class GroundingService:
    """
    High-Precision Claim-Level Grounding Verification Service for SAP BRIM Knowledge Assistant.
    Calibrated for senior 8+ years SAP BRIM consultants.
    Strictly verifies technical claims individually against retrieved evidence.
    """

    def __init__(self):
        self.grounding_threshold = settings.ANSWER_GROUNDING_THRESHOLD

    @staticmethod
    def _extract_sentences(text: str) -> List[str]:
        """Splits answer into discrete factual statements while filtering decorative formatting."""
        if not text:
            return []

        sentences = []
        for line in text.split("\n"):
            line = line.strip()
            # Ignore headers, table delimiters, and meta notices
            if not line or line.startswith("#") or line.startswith("|---") or line.startswith("---") or line.startswith("*All statements") or line.startswith("*(This"):
                continue
            # Strip list numbers or bullets
            clean_line = re.sub(r"^(\*|\-|\d+\.|\d+\))\s*", "", line).strip()
            if not clean_line:
                continue

            # Split on sentence boundaries (. ! ?)
            parts = re.split(r"(?<=[.!?])\s+", clean_line)
            for p in parts:
                p = p.strip()
                if len(p) >= 15:
                    sentences.append(p)

        return sentences

    @staticmethod
    def _extract_technical_identifiers(text: str) -> List[str]:
        """Extracts specific SAP T-codes and database tables."""
        tcodes = set()
        tables = set()

        for m in TCODE_PATTERN.finditer(text):
            tok = m.group(0).lower()
            if tok not in EXCLUDED_TECH_TOKENS and len(tok) >= 3:
                tcodes.add(tok)

        for m in TABLE_PATTERN.finditer(text):
            tok = m.group(0).lower()
            if tok not in EXCLUDED_TECH_TOKENS:
                tables.add(tok)

        return list(tcodes | tables)

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        pattern = rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])"
        return bool(re.search(pattern, text.lower()))

    @staticmethod
    def passes_gate(
        grounding_score: float,
        unsupported_claims: List[str],
        total_claims: int,
        hallucinated_ids: List[str],
        contradicted_claims: Optional[List[str]] = None,
        threshold: float = 0.80
    ) -> bool:
        if contradicted_claims is None:
            contradicted_claims = []
        return bool(
            grounding_score >= threshold
            and len(hallucinated_ids) == 0
            and len(contradicted_claims) == 0
            and len(unsupported_claims) <= max(1, int(total_claims * 0.25))
        )

    def verify_answer(
        self,
        query: str,
        answer: str,
        evidence_passages: List[Dict[str, Any]],
        source_type: str = "knowledge_base"
    ) -> Dict[str, Any]:
        """
        Performs claim-level grounding verification of the generated answer against evidence.
        Classifies each technical statement:
        - directly supported
        - supported with qualification
        - unsupported
        - contradicted
        """
        # Refusal or empty answer
        if source_type in ("refusal", "abstention") or not answer.strip():
            return {
                "grounding_score": 0.0,
                "passes_grounding_gate": False,
                "claims": [],
                "supported_claims": [],
                "unsupported_claims": [],
                "contradicted_claims": [],
                "critical_unsupported_claims": [],
                "all_material_claims_cited": False,
                "verification_status": "abstention" if source_type == "abstention" else "rejected",
                "summary": "Response is an abstention or scope refusal."
            }

        if not evidence_passages:
            return {
                "grounding_score": 0.0,
                "passes_grounding_gate": False,
                "claims": [],
                "supported_claims": [],
                "unsupported_claims": [],
                "contradicted_claims": [],
                "critical_unsupported_claims": [],
                "all_material_claims_cited": False,
                "verification_status": "unverified",
                "summary": "No supporting evidence available."
            }

        technical_checks_enabled = bool(getattr(settings, "TECHNICAL_CLAIM_VALIDATION_ENABLED", True))

        # Work on copies so evidence IDs used for marker resolution never leak back
        # into the caller's passages unless the caller assigned them.
        passages = [dict(p) for p in evidence_passages]
        if not any(p.get("evidence_id") for p in passages):
            assign_evidence_ids(passages)
        passage_by_id = {p["evidence_id"]: p for p in passages if p.get("evidence_id")}
        citable = [p for p in passages if not is_gap(p)]

        # Build concatenated evidence text & index passages
        combined_evidence = " ".join(
            (p.get("chunk_text") or p.get("snippet") or "").lower()
            for p in passages
        )
        evidence_tech_ids = set(self._extract_technical_identifiers(combined_evidence))
        query_release = release_context(query)

        # Extract material sentences as claims (markers stay attached to their sentence)
        sentences = self._extract_sentences(self._attach_trailing_markers(answer))
        if not sentences:
            sentences = [answer.strip()]

        claims_result = []
        supported_claims = []
        unsupported_claims = []
        contradicted_claims = []
        critical_unsupported = []
        uncited_standard_ids = []
        qualified_claims = []
        critical_failures: List[Dict[str, Any]] = []
        technical_validation: List[Dict[str, Any]] = []
        unsupported_causal_claims = []
        citation_checks = {"cited_claims": 0, "correct": 0, "mismatched": 0, "invalid_ids": [], "uncited_material_claims": 0}

        for raw_stmt in sentences:
            cited_ids = extract_marker_ids(raw_stmt)
            stmt = MARKER_PATTERN.sub("", raw_stmt).strip()
            if not stmt:
                continue
            if stmt.endswith("?"):
                # Clarification questions are not factual claims.
                claims_result.append({"claim": stmt, "status": "clarification", "supporting_source_ids": [],
                                      "reason": "Clarification question; not a factual claim.", "unsupported_technical_ids": []})
                continue
            stmt_lower = stmt.lower()
            raw_tokens = re.findall(r"\b[a-z0-9\/\-_]{3,}\b", stmt_lower)
            stmt_terms = [t for t in raw_tokens if t not in STOP_WORDS]
            is_limitation = sap_identifier_validator.is_limitation_statement(stmt)

            # Check technical identifiers in this statement
            stmt_tech_ids = self._extract_technical_identifiers(stmt)
            # A standard object name proves only that the identifier is plausible;
            # it does not prove the generated configuration or lifecycle claim.  A
            # technical instruction is publishable only when the exact identifier
            # also appears in the selected evidence for this answer.
            unsupported_stmt_tech = [] if is_limitation else [tid for tid in stmt_tech_ids if tid not in evidence_tech_ids]
            fabricated_stmt_tech = [
                tid for tid in unsupported_stmt_tech
                if tid not in VERIFIED_STANDARD_SAP_OBJECTS
                and not sap_entity_service.is_known_sap_identifier(tid)
            ]
            uncited_stmt_tech = [tid for tid in unsupported_stmt_tech if tid not in fabricated_stmt_tech]

            # Calculate overlap with evidence (combined, and per single passage)
            if stmt_terms:
                matched_terms = sum(1 for t in stmt_terms if self._contains_term(combined_evidence, t))
                overlap_ratio = matched_terms / len(stmt_terms)
            else:
                overlap_ratio = 1.0
            passage_overlaps = {}
            for p in citable:
                p_text = (p.get("chunk_text") or p.get("snippet") or "").lower()
                passage_overlaps[p.get("evidence_id")] = (
                    sum(1 for t in stmt_terms if self._contains_term(p_text, t)) / len(stmt_terms) if stmt_terms else 1.0
                )
            best_id = max(passage_overlaps, key=passage_overlaps.get) if passage_overlaps else None
            best_overlap = passage_overlaps.get(best_id, 0.0) if best_id else 0.0

            # Determine supporting sources
            supporting_source_ids = []
            for p in passages:
                p_text = (p.get("chunk_text") or p.get("snippet") or "").lower()
                if stmt_terms and sum(1 for t in stmt_terms if self._contains_term(p_text, t)) / len(stmt_terms) >= 0.20:
                    supporting_source_ids.append(p.get("source_id", p.get("evidence_id", "source")))

            # Claim-level technical identifier / procedure validation
            checks = []
            if technical_checks_enabled:
                checks = sap_identifier_validator.validate_sentence(stmt, passages, query=query)
                technical_validation.extend(c.to_dict() for c in checks)
            critical_checks = [c for c in checks if c.critical]
            other_failed_checks = [c for c in checks if not c.critical and c.status not in NON_FAILING_STATUSES]
            verified_check_ids = {eid for c in checks if c.status == "verified" for eid in c.evidence_ids}

            # Citation correctness: an attached marker must point at a passage that supports this claim.
            citation_status = None
            if cited_ids and technical_checks_enabled:
                valid = [c for c in cited_ids if c in passage_by_id]
                invalid = [c for c in cited_ids if c not in passage_by_id]
                citation_checks["invalid_ids"].extend(i for i in invalid if i not in citation_checks["invalid_ids"])
                citation_checks["cited_claims"] += 1
                cited_support = max((passage_overlaps.get(c, 0.0) for c in valid), default=0.0)
                # A passage cannot "support" a claim whose technical content it contradicts or
                # does not establish, however much vocabulary they share.
                if valid and not critical_checks and (cited_support >= 0.25 or verified_check_ids.intersection(valid)):
                    citation_status = "correct"
                    citation_checks["correct"] += 1
                else:
                    citation_status = "mismatch"
                    citation_checks["mismatched"] += 1
            elif not is_limitation and stmt_terms and technical_checks_enabled:
                citation_checks["uncited_material_claims"] += 1

            # Causal relationships must be supported on both sides by a single passage.
            causal_unsupported = False
            causal_critical = False
            causal = CAUSAL_CONNECTOR.search(stmt) if technical_checks_enabled and not is_limitation else None
            if causal:
                # Both sides must be linked within ONE evidence sentence that itself expresses a
                # causal/consequence relation; facts stated separately do not establish causation.
                left = content_terms(stmt[:causal.start()])
                right = content_terms(stmt[causal.end():])
                both_supported = False
                for p in citable:
                    for ev_sentence in self._evidence_sentences(passage_text(p)):
                        if not EVIDENCE_CAUSAL_MARKER.search(ev_sentence):
                            continue
                        s_terms = set(content_terms(ev_sentence))
                        l_ok = not left or sum(1 for t in left if t in s_terms) / len(left) >= 0.4
                        r_ok = not right or sum(1 for t in right if t in s_terms) / len(right) >= 0.4
                        if l_ok and r_ok:
                            both_supported = True
                            break
                    if both_supported:
                        break
                if not both_supported:
                    causal_unsupported = True
                    causal_critical = bool(PROCEDURE_EFFECT.search(stmt))
                    unsupported_causal_claims.append(stmt)

            # Release applicability of the best supporting passage
            release_applicability = "unspecified"
            if best_id and best_id in passage_by_id:
                bp = passage_by_id[best_id]
                # Scope from the sentence that supports the claim; a passage can discuss several releases.
                claim_terms = set(content_terms(stmt))
                support_sentence = max(
                    self._evidence_sentences(passage_text(bp)) or [""],
                    key=lambda s: len(claim_terms & set(content_terms(s))),
                )
                p_rel = release_context(support_sentence, str(bp.get("release") or ""))
                if not (p_rel["s4hana"] or p_rel["ecc"]):
                    p_rel = release_context(passage_text(bp), str(bp.get("document_name") or ""), str(bp.get("release") or ""))
                if not (p_rel["s4hana"] or p_rel["ecc"]) or not (query_release["s4hana"] or query_release["ecc"]):
                    release_applicability = "unspecified"
                elif (query_release["ecc"] and not query_release["s4hana"] and p_rel["s4hana"] and not p_rel["ecc"]) or (
                    query_release["s4hana"] and not query_release["ecc"] and p_rel["ecc"] and not p_rel["s4hana"]
                ):
                    release_applicability = "mismatch"
                else:
                    release_applicability = "matches"

            for c in critical_checks:
                critical_failures.append({
                    "claim": stmt, "identifier": c.identifier, "status": c.status,
                    "reason": c.reason, "evidence_ids": c.evidence_ids,
                })
            if causal_critical:
                critical_failures.append({
                    "claim": stmt, "identifier": None, "status": "unsupported_effect",
                    "reason": "The effect attributed to this maintenance action is not stated by any single evidence passage.",
                    "evidence_ids": [],
                })

            # Determine Claim Status
            if is_limitation and not critical_checks:
                status = "qualified"
                reason = "Explicitly qualified as unverified/unresolved; not counted as an unsupported claim."
                qualified_claims.append(stmt)
            elif any(c.status == "contradicted" for c in critical_checks):
                status = "contradicted"
                reason = next(c.reason for c in critical_checks if c.status == "contradicted")
                contradicted_claims.append(stmt)
                unsupported_claims.append(stmt)
            elif critical_checks:
                status = critical_checks[0].status
                reason = critical_checks[0].reason
                unsupported_claims.append(stmt)
            elif unsupported_stmt_tech:
                status = "unsupported"
                reason = f"Technical identifier(s) are absent from the selected evidence: {', '.join(unsupported_stmt_tech)}"
                unsupported_claims.append(stmt)
            elif other_failed_checks:
                status = "needs_qualification" if any(c.status == "conflicting_evidence" for c in other_failed_checks) else "unsupported"
                reason = other_failed_checks[0].reason
                unsupported_claims.append(stmt)
            elif release_applicability == "mismatch" and technical_checks_enabled and not (
                release_context(stmt)["s4hana"] or release_context(stmt)["ecc"]
            ):
                # Evidence for another product/release, applied without saying so.
                status = "needs_qualification"
                reason = "The supporting passage applies to a different SAP release than the question; the claim does not state that scope."
                unsupported_claims.append(stmt)
            elif causal_unsupported:
                status = "unsupported_causal"
                reason = "The causal relationship is not supported on both sides by a single evidence passage."
                unsupported_claims.append(stmt)
            elif citation_status == "mismatch":
                status = "citation_mismatch"
                reason = f"Cited evidence {', '.join(cited_ids)} does not support this claim (best match: {best_id})."
                unsupported_claims.append(stmt)
            elif overlap_ratio >= 0.25:
                status = "supported"
                reason = f"Evidence directly supports statement (overlap: {overlap_ratio:.2f})."
                supported_claims.append(stmt)
            elif overlap_ratio >= 0.12:
                status = "partially_supported"
                reason = f"Corroborated by evidence concepts (overlap: {overlap_ratio:.2f})."
                supported_claims.append(stmt)
            else:
                status = "unsupported"
                reason = f"Insufficient evidence support for statement (overlap: {overlap_ratio:.2f})."
                unsupported_claims.append(stmt)

            if not is_limitation:
                for ut in fabricated_stmt_tech:
                    if ut not in critical_unsupported:
                        critical_unsupported.append(ut)
                for ut in uncited_stmt_tech:
                    if ut not in uncited_standard_ids:
                        uncited_standard_ids.append(ut)

            claims_result.append({
                "claim": stmt,
                "status": status,
                "supporting_source_ids": supporting_source_ids[:3],
                "reason": reason,
                "unsupported_technical_ids": unsupported_stmt_tech,
                "cited_evidence_ids": cited_ids,
                "citation_status": citation_status,
                "best_evidence_id": best_id,
                "best_passage_overlap": round(best_overlap, 3),
                "release_applicability": release_applicability,
                "technical_checks": [c.to_dict() for c in checks],
            })

        # Qualified statements and clarification questions are honest limitations, not
        # factual claims; they neither support nor undermine the grounding score.
        material_claims = [c for c in claims_result if c["status"] not in ("qualified", "clarification")]

        # Calculate Grounding Score - calibrated to be honest and accurate
        total_claims = len(material_claims)
        if total_claims > 0:
            support_ratio = len(supported_claims) / total_claims
            if support_ratio >= 0.75:
                raw_grounding = 0.80 + 0.14 * min(1.0, (support_ratio - 0.75) / 0.25)
            elif support_ratio >= 0.55:
                raw_grounding = 0.70 + 0.10 * ((support_ratio - 0.55) / 0.20)
            elif support_ratio >= 0.35:
                raw_grounding = 0.55 + 0.15 * ((support_ratio - 0.35) / 0.20)
            else:
                raw_grounding = max(0.20, support_ratio * 1.0)
        else:
            raw_grounding = 0.50

        # Penalize if fabricated identifiers or completely unsupported claims are present
        technical_evidence_gaps = critical_unsupported + uncited_standard_ids + [
            f"{f['identifier']}:{f['status']}" for f in critical_failures
        ]
        if technical_evidence_gaps:
            penalty = min(0.30, len(technical_evidence_gaps) * 0.10)
            final_grounding_score = max(0.20, raw_grounding - penalty)
        elif len(unsupported_claims) > len(supported_claims):
            final_grounding_score = min(raw_grounding, 0.45)
        else:
            final_grounding_score = raw_grounding

        final_grounding_score = max(0.15, min(0.98, round(final_grounding_score, 2)))

        # Publication Rule:
        # 1. Grounding score >= ANSWER_GROUNDING_THRESHOLD (0.80)
        # 2. Every SAP technical identifier is present in selected evidence.
        # 3. Zero contradicted claims
        # 4. Material claim support consistency (unsupported claims <= 25% of total claims)
        # 5. Zero critical technical failures: a high score never overrides a failed
        #    critical claim (wrong operation, contradicted release, unsafe procedure, ...).
        passes_gate = bool(
            final_grounding_score >= self.grounding_threshold
            and len(critical_unsupported) == 0
            and len(uncited_standard_ids) == 0
            and len(contradicted_claims) == 0
            and len(critical_failures) == 0
            and len(unsupported_claims) <= max(1, int(total_claims * 0.25))
        )

        # Do not turn a localized evidence limitation into a whole-answer abstention;
        # source_type='abstention' is handled at the start of this verifier.
        if passes_gate:
            verification_status = "verified"
            summary = f"Verified answer with {final_grounding_score*100:.0f}% grounding across {len(supported_claims)}/{total_claims} claims."
        elif final_grounding_score >= 0.50:
            verification_status = "partial"
            summary = (
                f"Partially supported answer ({final_grounding_score*100:.0f}% grounding). "
                + (f"Unsupported technical identifiers: {', '.join(critical_unsupported)}." if critical_unsupported else "")
                + (f" Standard identifiers absent from selected evidence: {', '.join(uncited_standard_ids)}." if uncited_standard_ids else "")
                + (f" Critical technical claim failures: {len(critical_failures)}." if critical_failures else "")
            )
        else:
            verification_status = "unverified"
            summary = f"Verification failed ({final_grounding_score*100:.0f}% grounding < threshold {self.grounding_threshold*100:.0f}%)."

        return {
            "grounding_score": final_grounding_score,
            "passes_grounding_gate": passes_gate,
            "claims": claims_result,
            "supported_claims": supported_claims,
            "unsupported_claims": unsupported_claims,
            "contradicted_claims": contradicted_claims,
            "critical_unsupported_claims": critical_unsupported,
            "uncited_standard_ids": uncited_standard_ids,
            "all_material_claims_cited": len(supported_claims) == total_claims and total_claims > 0,
            "verification_status": verification_status,
            "summary": summary,
            # Claim-level validation details (admin/audit only; never shown to ordinary users)
            "qualified_claims": qualified_claims,
            "critical_failures": critical_failures,
            "technical_validation": technical_validation,
            "unsupported_causal_claims": unsupported_causal_claims,
            "citation_checks": citation_checks,
            "evidence_conflicts": (
                sap_identifier_validator.detect_evidence_conflicts(passages) if technical_checks_enabled else []
            ),
            "material_claim_count": total_claims,
        }

    @staticmethod
    def _evidence_sentences(text: str) -> List[str]:
        return [s for s in re.split(r"(?<=[.!?])\s+|\s*[●•]\s*", text or "") if len(s.strip()) >= 12]

    @staticmethod
    def _attach_trailing_markers(text: str) -> str:
        """Move "[E1]" written after sentence punctuation in front of it so it stays with its claim."""
        return re.sub(r"([.!?])\s*((?:\[E\d{1,3}(?:\s*,\s*E\d{1,3})*\]\s*)+)", lambda m: f" {m.group(2).strip()}{m.group(1)} ", text or "")


grounding_service = GroundingService()
