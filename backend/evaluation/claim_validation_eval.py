"""
Offline claim-validation evaluation (no LLM, web or database calls).

Runs reviewed cases from datasets/claim_validation_cases.json through the verifier and the
publication pipeline, then reports:
  - claim-label accuracy (factual accuracy of the verifier's per-claim judgement)
  - technical identifier accuracy (bad identifiers flagged / good identifiers not flagged)
  - evidence coverage (supported claims recognised as supported)
  - citation correctness (wrong citations detected, correct ones not flagged)
  - source authority classification and release applicability
  - contradiction detection, unsafe-procedure detection, causal/path/operation detection
  - publication decisions (false acceptance / false rejection) and appropriate abstention
  - repair success (scripted repair responses; bad content must not be published)
  - API and streaming contract compatibility

The harness only relies on keys that exist in both the pre-change and post-change code, so the
same file can be run against a baseline checkout to produce comparable numbers:

    python -m backend.evaluation.claim_validation_eval --label post_change
"""

import argparse
import json
import re
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

DATASET = Path(__file__).parent / "datasets" / "claim_validation_cases.json"
RESULTS_DIR = Path(__file__).parent / "results"
MARKER = re.compile(r"\s?\[E\d{1,3}(?:\s*,\s*E\d{1,3})*\]")
LEGACY_DONE_KEYS = {
    "answer", "source_type", "grounding_score", "is_in_rag_pipeline", "kb_score", "web_score", "winning_score",
    "source_scores", "selected_source", "verification_status", "internal_evidence_confidence",
    "selected_evidence_quality", "external_search_used", "citations", "web_sources", "images",
    "follow_up_questions", "selection_summary", "comparison_audit",
}


def ratio(num, den):
    return round(num / den, 4) if den else None


def case_passages(case, pool):
    rows = [dict(pool[k]) for k in case.get("evidence", [])] + [dict(p) for p in case.get("evidence_inline", [])]
    for i, row in enumerate(rows):
        row.setdefault("source_type", "knowledge_base")
        row.setdefault("score", 0.72)
        row.setdefault("rerank_score", row["score"])
        row.setdefault("snippet", row["chunk_text"][:350])
        row["evidence_id"] = f"E{i + 1}"
    return rows


def predicted_label(status):
    if status in ("supported", "partially_supported"):
        return "supported"
    if status in ("qualified", "clarification"):
        return "qualified"  # limitations and clarification questions are neither supported nor unsupported claims
    return "not_supported"


def find_claim(result, fragment):
    frag = fragment.lower()
    for c in result.get("claims", []):
        if frag in MARKER.sub("", c.get("claim", "")).lower():
            return c
    return None


def flagged(result, identifier):
    ident = identifier.lower()
    if ident in [i.lower() for i in result.get("critical_unsupported_claims", []) + result.get("uncited_standard_ids", [])]:
        return True
    return any(
        predicted_label(c.get("status")) == "not_supported" and ident in c.get("claim", "").lower()
        for c in result.get("claims", [])
    )


def legacy_finalize(grounding_service, query, answer, passages, repaired_text):
    """Pre-change publication flow: one repair, adopted if different, no further safeguards."""
    verification = grounding_service.verify_answer(query, answer, passages, source_type="knowledge_base")
    final = answer
    if not verification.get("passes_grounding_gate"):
        if repaired_text and repaired_text != final:
            verification = grounding_service.verify_answer(query, repaired_text, passages, source_type="knowledge_base")
            final = repaired_text
    return final, verification


def run_pipeline_stream(rag_module, settings, case, passages):
    """Drive stream_query and process_query with every external dependency mocked."""
    answer = case["answer"]
    repair_text = (case.get("repair") or {}).get("answer")
    rows = [{k: v for k, v in p.items() if k != "evidence_id"} for p in passages]

    def fake_stream(query, evidence, source_type="knowledge_base", **kwargs):
        for i in range(0, len(answer), 23):
            yield answer[i:i + 23]

    def fake_generate(query, evidence, source_type="knowledge_base", **kwargs):
        return answer

    def fake_repair(**kwargs):
        return repair_text if repair_text else kwargs.get("candidate_answer")

    rag = rag_module.rag_service
    with ExitStack() as stack:
        for name, value in (("AUTO_MULTI_SOURCE_FALLBACK", False), ("WEB_FALLBACK_ENABLED", False),
                            ("MULTI_SOURCE_COMPARE_ENABLED", False), ("REPO_SOURCE_ENABLED", False)):
            stack.enter_context(patch.object(settings, name, value))
        stack.enter_context(patch.object(rag.retrieval, "retrieve", side_effect=lambda db, q, top_k=15: [dict(r) for r in rows]))
        stack.enter_context(patch.object(rag.retrieval, "hybrid_search", side_effect=lambda db, q, top_k=None, **kw: [dict(r) for r in rows]))
        stack.enter_context(patch.object(rag_module.reranking_service, "rerank_kb",
                                         side_effect=lambda q, c, top_n=4: ([dict(x) for x in c][:max(top_n, 1)], 0.72, True)))
        stack.enter_context(patch.object(rag_module.llm_service, "stream_answer", side_effect=fake_stream))
        stack.enter_context(patch.object(rag_module.llm_service, "generate_answer", side_effect=fake_generate))
        stack.enter_context(patch.object(rag_module.llm_service, "repair_answer", side_effect=fake_repair))
        events = list(rag.stream_query(db=MagicMock(), query=case["question"]))
        result = rag.process_query(db=MagicMock(), query=case["question"])
    return events, result


def evaluate(label):
    import importlib
    from backend.app.config import settings
    # The services package re-exports a `rag_service` instance; import the module itself.
    rag_module = importlib.import_module("backend.app.services.rag_service")
    from backend.app.services.grounding_service import grounding_service
    from backend.app.services.web_search_service import WebSearchService

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    pool = data["evidence_pool"]
    has_finalize = hasattr(rag_module.RAGService, "_finalize_answer")

    m = {
        "claims_total": 0, "claims_correct": 0,
        "supported_total": 0, "supported_recognised": 0,
        "not_supported_total": 0, "not_supported_detected": 0,
        "qualified_total": 0, "qualified_not_penalised": 0,
        "kind": {},
        "citation_mismatch_total": 0, "citation_mismatch_detected": 0,
        "citation_correct_total": 0, "citation_false_alarms": 0,
        "release_mismatch_total": 0, "release_mismatch_detected": 0,
        "contradiction_total": 0, "contradiction_detected": 0,
        "ids_flag_total": 0, "ids_flag_detected": 0, "ids_ok_total": 0, "ids_ok_false_flags": 0,
        "gate_total": 0, "gate_correct": 0, "bad_answers": 0, "bad_published_verified": 0,
        "good_answers": 0, "good_rejected": 0,
        "repair_total": 0, "repair_success": 0,
        "compat_total": 0, "compat_pass": 0,
        "authority_total": 0, "authority_correct": 0,
        "by_level": {},
    }
    details = []

    for case in data["cases"]:
        passages = case_passages(case, pool)
        result = grounding_service.verify_answer(case["question"], case["answer"], passages, source_type="knowledge_base")
        case_detail = {"id": case["id"], "level": case["level"], "gate": result.get("passes_grounding_gate"),
                       "score": result.get("grounding_score"), "claims": []}

        for label_row in case["claims"]:
            claim = find_claim(result, label_row["fragment"])
            status = claim.get("status") if claim else None
            pred = predicted_label(status) if claim else "missing"
            exp = label_row["expected"]
            ok = (pred == exp) or (exp == "qualified" and pred in ("qualified", "supported"))
            m["claims_total"] += 1
            m["claims_correct"] += int(ok)
            if exp == "supported":
                m["supported_total"] += 1
                m["supported_recognised"] += int(pred == "supported")
            elif exp == "not_supported":
                m["not_supported_total"] += 1
                m["not_supported_detected"] += int(pred == "not_supported")
                kind = label_row.get("kind") or "unsupported"
                k = m["kind"].setdefault(kind, {"total": 0, "detected": 0})
                k["total"] += 1
                k["detected"] += int(pred == "not_supported")
            else:
                m["qualified_total"] += 1
                m["qualified_not_penalised"] += int(ok)
            if label_row.get("kind") == "contradicted":
                m["contradiction_total"] += 1
                m["contradiction_detected"] += int(bool(claim) and (
                    status == "contradicted" or claim.get("claim") in result.get("contradicted_claims", [])))
            if label_row.get("citation") == "mismatch":
                m["citation_mismatch_total"] += 1
                m["citation_mismatch_detected"] += int(bool(claim) and claim.get("citation_status") == "mismatch")
            elif label_row.get("citation") == "correct":
                m["citation_correct_total"] += 1
                m["citation_false_alarms"] += int(bool(claim) and claim.get("citation_status") == "mismatch")
            if label_row.get("release") == "mismatch":
                m["release_mismatch_total"] += 1
                m["release_mismatch_detected"] += int(bool(claim) and claim.get("release_applicability") == "mismatch")
            case_detail["claims"].append({"fragment": label_row["fragment"], "expected": exp, "status": status, "ok": ok})

        for ident in case["identifiers"]["flag"]:
            m["ids_flag_total"] += 1
            m["ids_flag_detected"] += int(flagged(result, ident))
        for ident in case["identifiers"]["ok"]:
            m["ids_ok_total"] += 1
            m["ids_ok_false_flags"] += int(flagged(result, ident))

        expected_publish = case["expect_publish_verified"]
        published = bool(result.get("passes_grounding_gate"))
        m["gate_total"] += 1
        m["gate_correct"] += int(published == expected_publish)
        lvl = m["by_level"].setdefault(case["level"], {"cases": 0, "gate_correct": 0, "claims": 0, "claims_correct": 0})
        lvl["cases"] += 1
        lvl["gate_correct"] += int(published == expected_publish)
        lvl["claims"] += len(case["claims"])
        lvl["claims_correct"] += sum(1 for c in case_detail["claims"] if c["ok"])
        if expected_publish:
            m["good_answers"] += 1
            m["good_rejected"] += int(not published)
        else:
            m["bad_answers"] += 1
            m["bad_published_verified"] += int(published)

        # Repair: scripted repair response; bad content must not reach the published answer.
        if case.get("repair"):
            m["repair_total"] += 1
            repaired_text = case["repair"]["answer"]
            if has_finalize:
                from backend.app.services.restriction_scope_classifier import restriction_scope_classifier
                scope = restriction_scope_classifier.classify(case["question"])
                scope = scope if scope.is_restriction_query else None
                with patch.object(rag_module.llm_service, "repair_answer", return_value=repaired_text):
                    final, verification, _repair, _status = rag_module.rag_service._finalize_answer(
                        case["question"], case["answer"], passages, "knowledge_base", scope, None)
            else:
                final, verification = legacy_finalize(grounding_service, case["question"], case["answer"], passages, repaired_text)
            leaked = [s for s in case["repair"]["must_not_contain"] if s.lower() in final.lower()]
            success = not leaked
            m["repair_success"] += int(success)
            case_detail["repair"] = {"success": success, "leaked": leaked,
                                     "final_gate": verification.get("passes_grounding_gate")}
        details.append(case_detail)

    # API / streaming contract on representative cases.
    for case in [c for c in data["cases"] if c["id"] in ("S1", "I3", "A1", "A2")]:
        m["compat_total"] += 1
        try:
            events, result = run_pipeline_stream(rag_module, settings, case, case_passages(case, pool))
            types = [e.get("type") for e in events]
            done = events[-1] if events else {}
            ok = (
                bool(events) and types[-1] == "done" and "token" in types and types.index("token") < len(types) - 1
                and LEGACY_DONE_KEYS <= set(done) and bool(done.get("answer"))
                and LEGACY_DONE_KEYS <= set(result) and bool(result.get("answer"))
            )
        except Exception as exc:  # report, do not hide
            ok = False
            details.append({"id": case["id"], "compat_error": repr(exc)})
        m["compat_pass"] += int(ok)

    # Source authority classification through the web search normalization path.
    for item in data["authority_cases"]:
        service = WebSearchService.__new__(WebSearchService)
        service.api_key, service._cache, service._cache_ttl = "test", {}, 3600
        service.client = MagicMock()
        service.client.search.return_value = {"results": [{"url": item["url"], "title": "T", "content": "SAP content."}]}
        with patch.object(settings, "WEB_FALLBACK_ENABLED", True):
            rows = service.search_sap_authoritative(f"authority probe {item['url']}")
        row = rows[0] if rows else {}
        if "authority_class" in row:
            official = row["authority_class"] in ("official_sap_help", "sap_support_note")
        else:
            official = row.get("domain") == "help.sap.com" or row.get("authority_tier") == 1
        m["authority_total"] += 1
        m["authority_correct"] += int(official == item["official"])

    return {
        "label": label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(data["cases"]),
        "claim_label_accuracy": ratio(m["claims_correct"], m["claims_total"]),
        "evidence_coverage_supported_recognised": ratio(m["supported_recognised"], m["supported_total"]),
        "unsupported_claim_detection": ratio(m["not_supported_detected"], m["not_supported_total"]),
        "qualified_statements_not_penalised": ratio(m["qualified_not_penalised"], m["qualified_total"]),
        "detection_by_failure_kind": {k: ratio(v["detected"], v["total"]) for k, v in sorted(m["kind"].items())},
        "technical_identifier_recall": ratio(m["ids_flag_detected"], m["ids_flag_total"]),
        "technical_identifier_false_flag_rate": ratio(m["ids_ok_false_flags"], m["ids_ok_total"]),
        "contradiction_detection": ratio(m["contradiction_detected"], m["contradiction_total"]),
        "citation_mismatch_detection": ratio(m["citation_mismatch_detected"], m["citation_mismatch_total"]),
        "citation_false_alarm_rate": ratio(m["citation_false_alarms"], m["citation_correct_total"]),
        "release_mismatch_detection": ratio(m["release_mismatch_detected"], m["release_mismatch_total"]),
        "source_authority_classification": ratio(m["authority_correct"], m["authority_total"]),
        "publication_decision_accuracy": ratio(m["gate_correct"], m["gate_total"]),
        "false_acceptance_rate": ratio(m["bad_published_verified"], m["bad_answers"]),
        "false_rejection_rate": ratio(m["good_rejected"], m["good_answers"]),
        "repair_success": ratio(m["repair_success"], m["repair_total"]),
        "api_streaming_compatibility": ratio(m["compat_pass"], m["compat_total"]),
        "by_level": {
            lvl: {"publication_decision_accuracy": ratio(v["gate_correct"], v["cases"]),
                  "claim_label_accuracy": ratio(v["claims_correct"], v["claims"]), "cases": v["cases"]}
            for lvl, v in m["by_level"].items()
        },
        "counts": {k: v for k, v in m.items() if isinstance(v, int)},
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="post_change")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    summary = evaluate(args.label)
    out = Path(args.out) if args.out else RESULTS_DIR / f"claim_validation_{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("details", "counts")}, indent=2))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
