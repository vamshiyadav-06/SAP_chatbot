import os
import sys
import json
import time
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from collections import defaultdict

# Ensure sys.path includes project root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.app.database import SessionLocal, init_db
from backend.app.services.rag_service import rag_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.llm_service import llm_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.sap_classifier import sap_classifier
from backend.app.config import settings
from backend.evaluation.answer_quality_evaluator import answer_quality_evaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("baseline_full")

DATASET_FILE = Path(__file__).resolve().parent / "datasets" / "dev_questions.jsonl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RAW_OUTPUT_FILE = RESULTS_DIR / "baseline_dev_full.jsonl"
SUMMARY_OUTPUT_FILE = RESULTS_DIR / "baseline_dev_summary.json"


def load_dev_dataset() -> List[Dict[str, Any]]:
    items = []
    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def load_cached_results() -> Dict[str, Dict[str, Any]]:
    """Loads already completed results from RAW_OUTPUT_FILE to enable resumability."""
    cached = {}
    if RAW_OUTPUT_FILE.exists():
        with open(RAW_OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        qid = record.get("id")
                        if qid:
                            cached[qid] = record
                    except Exception:
                        pass
        logger.info(f"Loaded {len(cached)} cached question results from {RAW_OUTPUT_FILE}")
    return cached


def bootstrap_ci(values: List[float], n_resamples: int = 1000, alpha: float = 0.05) -> Tuple[float, float, float]:
    """Computes 95% bootstrap confidence interval (mean, lower, upper) with 1,000 resamples."""
    if not values:
        return 0.0, 0.0, 0.0
    if len(values) == 1:
        v = round(values[0], 4)
        return v, v, v

    mean_val = sum(values) / len(values)
    rng = random.Random(42)
    sample_means = []
    n = len(values)
    for _ in range(n_resamples):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        sample_means.append(sum(sample) / n)

    sample_means.sort()
    low_idx = int((alpha / 2.0) * n_resamples)
    high_idx = int((1.0 - alpha / 2.0) * n_resamples)
    return round(mean_val, 4), round(sample_means[low_idx], 4), round(sample_means[high_idx], 4)


def evaluate_retrieval(
    retrieved_candidates: List[Dict[str, Any]],
    gold_chunk_ids: List[str],
    module_tags: List[str]
) -> Dict[str, Any]:
    """
    Computes Recall@3, @5, @10 defined as FRACTION of gold chunks retrieved,
    Hit-Rate@3, @5, @10, MRR, and per-module coverage for multi-module questions.
    """
    if not gold_chunk_ids:
        return {
            "has_gold": False,
            "recall_at_3": None,
            "recall_at_5": None,
            "recall_at_10": None,
            "hit_at_3": None,
            "hit_at_5": None,
            "hit_at_10": None,
            "mrr": None,
            "module_coverage": None
        }

    gold_set = set(gold_chunk_ids)
    num_gold = len(gold_set)
    retrieved_ids = [c.get("chunk_id") or c.get("id") for c in retrieved_candidates if (c.get("chunk_id") or c.get("id"))]


    # Fractions retrieved
    ret_3 = set(retrieved_ids[:3])
    ret_5 = set(retrieved_ids[:5])
    ret_10 = set(retrieved_ids[:10])

    frac_3 = len(ret_3 & gold_set) / num_gold
    frac_5 = len(ret_5 & gold_set) / num_gold
    frac_10 = len(ret_10 & gold_set) / num_gold

    hit_3 = 1.0 if (ret_3 & gold_set) else 0.0
    hit_5 = 1.0 if (ret_5 & gold_set) else 0.0
    hit_10 = 1.0 if (ret_10 & gold_set) else 0.0

    # MRR
    mrr = 0.0
    for rank, cid in enumerate(retrieved_ids, 1):
        if cid in gold_set:
            mrr = 1.0 / rank
            break

    # Multi-module coverage: check module presence across retrieved chunks
    module_cov = 1.0
    clean_modules = [m.upper().strip() for m in module_tags if m.upper().strip() not in ("GENERAL SAP BRIM", "GENERAL")]
    if len(clean_modules) > 1:
        covered_mods = set()
        for c in retrieved_candidates[: settings.TOP_K]:
            text = (c.get("chunk_text") or c.get("snippet") or "") + " " + (c.get("document_name") or "")
            text_upper = text.upper()
            for mod in clean_modules:
                if mod in text_upper:
                    covered_mods.add(mod)
        module_cov = len(covered_mods) / len(clean_modules)

    return {
        "has_gold": True,
        "gold_count": num_gold,
        "recall_at_3": round(frac_3, 4),
        "recall_at_5": round(frac_5, 4),
        "recall_at_10": round(frac_10, 4),
        "hit_at_3": hit_3,
        "hit_at_5": hit_5,
        "hit_at_10": hit_10,
        "mrr": round(mrr, 4),
        "module_coverage": round(module_cov, 4)
    }


def evaluate_refusal_or_false_premise(
    category: str,
    query: str,
    answer: str,
    verification_status: str
) -> Dict[str, Any]:
    """
    Evaluates out_of_scope_refusal, corpus_cannot_answer, and false_premise questions:
    - Did the model refuse/abstain correctly?
    - Did it correct the false premise?
    """
    ans_lower = answer.lower()
    refusal_markers = [
        "cannot be answered", "not documented in", "only help with sap", "only assist with sap",
        "outside my scope", "confidential", "unable to answer",
        "does not exist in standard sap", "abstain", "insufficient evidence"
    ]
    correction_markers = [
        "premise of this question is incorrect", "statement is factually incorrect",
        "error in the question", "incorrect assumption", "does not execute",
        "table dfkkop is not", "rating is performed by sap cc", "not configured inside sap sd"
    ]

    is_refused = verification_status in ("abstention", "refusal", "rejected") or any(m in ans_lower for m in refusal_markers)
    corrected_premise = any(m in ans_lower for m in correction_markers)

    if category in ("out_of_scope_refusal", "corpus_cannot_answer"):
        success = 1.0 if is_refused else 0.0
    elif category == "false_premise":
        success = 1.0 if (corrected_premise or is_refused) else 0.0
    else:
        success = 1.0

    return {
        "is_refused_or_abstained": is_refused,
        "corrected_premise": corrected_premise,
        "refusal_or_correction_success": success
    }


def run_full_baseline():
    init_db()
    db = SessionLocal()

    questions = load_dev_dataset()
    cached_results = load_cached_results()
    total_q = len(questions)

    logger.info(f"=== STARTING FULL DEV BASELINE EVALUATION ({total_q} questions) ===")
    logger.info(f"Production TOP_K = {settings.TOP_K}")

    evaluated_records = []
    # Open raw jsonl file in append mode
    raw_file = open(RAW_OUTPUT_FILE, "a" if cached_results else "w", encoding="utf-8")

    try:
        for idx, item in enumerate(questions, 1):
            qid = item["id"]
            query = item["query"]
            cat = item.get("category", "general")
            gold_chunks = item.get("gold_chunk_ids", [])
            module_tags = item.get("module_tags", [])
            must_cover_facts = item.get("must_cover_key_facts", [])
            expected_ids = item.get("expected_identifiers", [])
            ref_ans = item.get("reference_answer", "")

            # If already cached, load and continue
            if qid in cached_results:
                logger.info(f"[{idx}/{total_q}] Resuming cached {qid} [{cat}]")
                evaluated_records.append(cached_results[qid])
                continue

            logger.info(f"[{idx}/{total_q}] Evaluating {qid} [{cat}]: '{query[:60]}'...")

            # Stage timings dict
            stage_timings = {}
            t_total_start = time.perf_counter()

            # 1. Retrieval Stage (Top 10 candidates retrieved for evaluation)
            t_ret_start = time.perf_counter()
            top_10_candidates = retrieval_service.hybrid_search(db, query, top_k=10)
            stage_timings["retrieval_ms"] = round((time.perf_counter() - t_ret_start) * 1000, 2)

            ret_eval = evaluate_retrieval(top_10_candidates, gold_chunks, module_tags)

            # 2. End-to-End Generation & Verification
            t_gen_start = time.perf_counter()
            rag_res = rag_service.process_query(db, query)
            stage_timings["generation_and_verification_ms"] = round((time.perf_counter() - t_gen_start) * 1000, 2)
            stage_timings["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 2)

            candidate_answer = rag_res.get("answer", "")
            verification_status = rag_res.get("verification_status", "verified")
            grounding_score = rag_res.get("grounding_score", 0.0)
            model_used = rag_res.get("model_used", getattr(llm_service, "last_model_used", "openai/gpt-oss-120b"))
            failed_over = rag_res.get("failed_over", getattr(llm_service, "failed_over", False))
            regen_count = rag_res.get("regeneration_count", 0)

            # Re-run failed-over questions on primary model with backoff as requested
            if failed_over and not rag_res.get("source_type") in ("refusal", "abstention"):
                logger.info(f"Question {qid} failed over to {model_used}. Retrying primary model with backoff...")
                primary_ans = llm_service.generate_with_primary_model(
                    query=query,
                    evidence=top_10_candidates[: settings.TOP_K],
                    source_type=rag_res.get("source_type", "knowledge_base")
                )
                if primary_ans:
                    logger.info(f"Primary model retry SUCCESS for {qid}!")
                    candidate_answer = primary_ans
                    model_used = llm_service.GROQ_MODELS[0]
                    failed_over = False

            # 3. Refusal & False Premise Scoring
            ref_eval = evaluate_refusal_or_false_premise(
                category=cat,
                query=query,
                answer=candidate_answer,
                verification_status=verification_status
            )

            # 4. Key-Fact Coverage (Excluded for out_of_scope and corpus_cannot_answer refusals)
            apply_key_fact = cat not in ("out_of_scope_refusal", "corpus_cannot_answer")
            if apply_key_fact:
                cov_res = answer_quality_evaluator.evaluate_key_fact_coverage(candidate_answer, must_cover_facts)
                key_fact_cov = cov_res["key_fact_coverage"]
                covered_facts = cov_res["covered_facts"]
                missing_facts = cov_res["missing_facts"]
            else:
                key_fact_cov = None
                covered_facts = []
                missing_facts = []

            # 5. Judge Correctness
            judge_res = answer_quality_evaluator.evaluate_llm_judge_correctness(
                query=query,
                reference_answer=ref_ans,
                must_cover_key_facts=must_cover_facts if apply_key_fact else [],
                candidate_answer=candidate_answer,
                generator_model=model_used
            )

            # 6. Technical Identifiers
            evidence_text = " ".join([c.get("chunk_text", "") for c in top_10_candidates[: settings.TOP_K]])
            id_res = answer_quality_evaluator.evaluate_identifiers(
                answer=candidate_answer,
                expected_ids=expected_ids,
                evidence_text=evidence_text
            )

            # 7. Faithfulness
            faith_res = answer_quality_evaluator.evaluate_faithfulness(rag_res)

            # Construct raw record
            record = {
                "id": qid,
                "category": cat,
                "module_tags": module_tags,
                "query": query,
                "answer": candidate_answer,
                "model_used": model_used,
                "failed_over": failed_over,
                "judge_model": judge_res["judge_model"],
                "regeneration_count": regen_count,
                "stage_timings": stage_timings,
                "retrieved_chunk_ids": [c.get("chunk_id") or c.get("id") for c in top_10_candidates[: settings.TOP_K]],
                "retrieved_scores": [c.get("score", 0.0) for c in top_10_candidates[: settings.TOP_K]],
                "grounding_score": grounding_score,
                "verification_status": verification_status,
                "retrieval_metrics": ret_eval,
                "refusal_metrics": ref_eval,
                "key_fact_coverage": key_fact_cov,
                "covered_facts": covered_facts,
                "missing_facts": missing_facts,
                "llm_judge_score": judge_res["llm_judge_score"],
                "identifier_precision": id_res["identifier_precision"],
                "id_precision_num": id_res["identifier_precision_numerator"],
                "id_precision_den": id_res["identifier_precision_denominator"],
                "identifier_recall": id_res["identifier_recall"],
                "id_recall_num": id_res["identifier_recall_numerator"],
                "id_recall_den": id_res["identifier_recall_denominator"],
                "supported_claim_rate": faith_res["supported_claim_rate"],
                "unsupported_claim_rate": faith_res["unsupported_claim_rate"],
                "contradicted_claim_rate": faith_res["contradicted_claim_rate"]
            }

            # Cache line-by-line
            raw_file.write(json.dumps(record) + "\n")
            raw_file.flush()
            evaluated_records.append(record)

    finally:
        raw_file.close()

    # Aggregate Full Metrics & Bootstrap CIs
    logger.info("Computing aggregate metrics with 95% bootstrap confidence intervals...")
    summary = aggregate_and_summarize(evaluated_records)

    with open(SUMMARY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Saved full dev baseline results to {RAW_OUTPUT_FILE}")
    logger.info(f"Saved summary metrics to {SUMMARY_OUTPUT_FILE}")

    return summary


def aggregate_and_summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_q = len(records)

    # Retrieval lists (only for questions with gold chunks)
    gold_q = [r for r in records if r["retrieval_metrics"]["has_gold"]]
    rec_3 = [r["retrieval_metrics"]["recall_at_3"] for r in gold_q]
    rec_5 = [r["retrieval_metrics"]["recall_at_5"] for r in gold_q]
    rec_10 = [r["retrieval_metrics"]["recall_at_10"] for r in gold_q]
    hit_3 = [r["retrieval_metrics"]["hit_at_3"] for r in gold_q]
    hit_5 = [r["retrieval_metrics"]["hit_at_5"] for r in gold_q]
    hit_10 = [r["retrieval_metrics"]["hit_at_10"] for r in gold_q]
    mrr_list = [r["retrieval_metrics"]["mrr"] for r in gold_q]
    mod_cov = [r["retrieval_metrics"]["module_coverage"] for r in gold_q if r["retrieval_metrics"]["module_coverage"] is not None]

    # Key-fact lists (excluding out_of_scope and unanswerable refusals)
    fact_q = [r for r in records if r["key_fact_coverage"] is not None]
    fact_cov = [r["key_fact_coverage"] for r in fact_q]

    # Refusals & False Premise
    refusal_q = [r for r in records if r["category"] in ("out_of_scope_refusal", "corpus_cannot_answer", "false_premise")]
    refusal_scores = [r["refusal_metrics"]["refusal_or_correction_success"] for r in refusal_q]

    # Quality and Faithfulness
    judge_scores = [r["llm_judge_score"] for r in records]
    supp_rates = [r["supported_claim_rate"] for r in records]
    unsupp_rates = [r["unsupported_claim_rate"] for r in records]

    # Identifiers
    id_prec_list = [r["identifier_precision"] for r in records]
    id_rec_list = [r["identifier_recall"] for r in records]
    total_id_prec_num = sum(r["id_precision_num"] for r in records)
    total_id_prec_den = sum(r["id_precision_den"] for r in records)
    total_id_rec_num = sum(r["id_recall_num"] for r in records)
    total_id_rec_den = sum(r["id_recall_den"] for r in records)

    # Latencies
    latencies = [r["stage_timings"]["total_ms"] for r in records]
    latencies.sort()
    p50_lat = latencies[len(latencies) // 2] if latencies else 0.0
    p95_lat = latencies[int(len(latencies) * 0.95)] if latencies else 0.0

    # Model distribution & failover
    model_counts = defaultdict(int)
    for r in records:
        model_counts[r["model_used"]] += 1
    model_dist = {m: {"count": c, "percentage": round((c / total_q) * 100, 2)} for m, c in model_counts.items()}
    failed_over_count = sum(1 for r in records if r["failed_over"])

    # Per-category summary
    cat_groups = defaultdict(list)
    for r in records:
        cat_groups[r["category"]].append(r)

    categories_summary = {}
    for cat, items in sorted(cat_groups.items()):
        cat_gold = [it for it in items if it["retrieval_metrics"]["has_gold"]]
        cat_facts = [it for it in items if it["key_fact_coverage"] is not None]
        cat_refusals = [it for it in items if it["category"] in ("out_of_scope_refusal", "corpus_cannot_answer", "false_premise")]
        categories_summary[cat] = {
            "count": len(items),
            "recall_at_3": round(sum(it["retrieval_metrics"]["recall_at_3"] for it in cat_gold) / len(cat_gold), 4) if cat_gold else None,
            "hit_rate_at_3": round(sum(it["retrieval_metrics"]["hit_at_3"] for it in cat_gold) / len(cat_gold), 4) if cat_gold else None,
            "mrr": round(sum(it["retrieval_metrics"]["mrr"] for it in cat_gold) / len(cat_gold), 4) if cat_gold else None,
            "key_fact_coverage": round(sum(it["key_fact_coverage"] for it in cat_facts) / len(cat_facts), 4) if cat_facts else None,
            "llm_judge_score": round(sum(it["llm_judge_score"] for it in items) / len(items), 4),
            "refusal_success": round(sum(it["refusal_metrics"]["refusal_or_correction_success"] for it in cat_refusals) / len(cat_refusals), 4) if cat_refusals else None,
            "unsupported_claim_rate": round(sum(it["unsupported_claim_rate"] for it in items) / len(items), 4),
            "id_precision": round(sum(it["identifier_precision"] for it in items) / len(items), 4),
            "latency_p50_ms": round(sorted([it["stage_timings"]["total_ms"] for it in items])[len(items) // 2], 2)
        }

    return {
        "dataset_split": "dev",
        "total_questions": total_q,
        "retrieval_evaluated_questions": len(gold_q),
        "excluded_retrieval_questions": total_q - len(gold_q),
        "model_distribution": model_dist,
        "failed_over_percentage": round((failed_over_count / total_q) * 100, 2),
        "metrics": {
            "Recall_at_3_fraction": {"mean": bootstrap_ci(rec_3)[0], "ci_95": bootstrap_ci(rec_3)[1:], "denominator": f"all gold chunks across {len(gold_q)} questions"},
            "Recall_at_5_fraction": {"mean": bootstrap_ci(rec_5)[0], "ci_95": bootstrap_ci(rec_5)[1:], "denominator": f"all gold chunks across {len(gold_q)} questions"},
            "Recall_at_10_fraction": {"mean": bootstrap_ci(rec_10)[0], "ci_95": bootstrap_ci(rec_10)[1:], "denominator": f"all gold chunks across {len(gold_q)} questions"},
            "Hit_Rate_at_3": {"mean": bootstrap_ci(hit_3)[0], "ci_95": bootstrap_ci(hit_3)[1:], "denominator": f"{len(gold_q)} questions with gold chunks"},
            "Hit_Rate_at_5": {"mean": bootstrap_ci(hit_5)[0], "ci_95": bootstrap_ci(hit_5)[1:], "denominator": f"{len(gold_q)} questions with gold chunks"},
            "Hit_Rate_at_10": {"mean": bootstrap_ci(hit_10)[0], "ci_95": bootstrap_ci(hit_10)[1:], "denominator": f"{len(gold_q)} questions with gold chunks"},
            "MRR": {"mean": bootstrap_ci(mrr_list)[0], "ci_95": bootstrap_ci(mrr_list)[1:], "denominator": f"{len(gold_q)} questions with gold chunks"},
            "Multi_Module_Coverage": {"mean": bootstrap_ci(mod_cov)[0], "ci_95": bootstrap_ci(mod_cov)[1:], "denominator": f"{len(mod_cov)} multi-module questions"},
            "Key_Fact_Coverage": {"mean": bootstrap_ci(fact_cov)[0], "ci_95": bootstrap_ci(fact_cov)[1:], "denominator": f"{len(fact_q)} factual questions (refusals excluded)"},
            "LLM_Judge_Correctness": {"mean": bootstrap_ci(judge_scores)[0], "ci_95": bootstrap_ci(judge_scores)[1:], "denominator": f"{total_q} questions"},
            "Refusal_and_Correction_Success": {"mean": bootstrap_ci(refusal_scores)[0], "ci_95": bootstrap_ci(refusal_scores)[1:], "denominator": f"{len(refusal_q)} refusal & false-premise questions"},
            "Supported_Claim_Rate": {"mean": bootstrap_ci(supp_rates)[0], "ci_95": bootstrap_ci(supp_rates)[1:], "denominator": f"all claims across {total_q} questions"},
            "Unsupported_Claim_Rate": {"mean": bootstrap_ci(unsupp_rates)[0], "ci_95": bootstrap_ci(unsupp_rates)[1:], "denominator": f"all claims across {total_q} questions"},
            "Identifier_Precision": {"mean": bootstrap_ci(id_prec_list)[0], "ci_95": bootstrap_ci(id_prec_list)[1:], "denominator": f"{total_id_prec_den} technical identifiers claimed"},
            "Identifier_Recall": {"mean": bootstrap_ci(id_rec_list)[0], "ci_95": bootstrap_ci(id_rec_list)[1:], "denominator": f"{total_id_rec_den} expected technical identifiers"},
            "Latency_p50_ms": round(p50_lat, 2),
            "Latency_p95_ms": round(p95_lat, 2)
        },
        "categories": categories_summary
    }


if __name__ == "__main__":
    run_full_baseline()
