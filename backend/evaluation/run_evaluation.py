import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

# Ensure sys.path includes project root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.database import SessionLocal, init_db
from backend.app.services.rag_service import rag_service
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.config import settings
from backend.evaluation.retrieval_evaluator import retrieval_evaluator
from backend.evaluation.grounding_evaluator import grounding_evaluator
from backend.evaluation.citation_evaluator import citation_evaluator
from backend.evaluation.followup_evaluator import followup_evaluator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("evaluation")

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "sap_brim_questions.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "evaluation_results.json"


def load_dataset() -> List[Dict[str, Any]]:
    items = []
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def run_benchmark(sample_size: int = 35) -> Dict[str, Any]:
    """
    Executes benchmark evaluation against the reviewed SAP BRIM dataset.
    Evaluates 10 distinct metrics across all question categories.
    """
    init_db()
    db = SessionLocal()
    dataset = load_dataset()

    # Stratified selection across categories to ensure comprehensive coverage
    categories = {}
    for item in dataset:
        cat = item.get("category", "general")
        categories.setdefault(cat, []).append(item)

    selected_test_cases = []
    per_cat = max(2, sample_size // len(categories))
    for cat, items in categories.items():
        selected_test_cases.extend(items[:per_cat])

    logger.info(f"Running evaluation benchmark on {len(selected_test_cases)} representative SAP questions...")

    # Metric accumulators
    recall_at_5_list = []
    context_precision_list = []
    context_recall_list = []
    grounding_score_list = []
    citation_correctness_list = []
    tech_id_accuracy_list = []
    followup_relevance_list = []
    abstention_quality_list = []
    sufficiency_list = []

    # Tavily trigger confusion matrix
    tavily_tp = 0
    tavily_fp = 0
    tavily_tn = 0
    tavily_fn = 0

    evaluated_cases = []

    for idx, case in enumerate(selected_test_cases, 1):
        query = case["query"]
        category = case.get("category", "")
        keywords = case.get("keywords", [])
        should_trigger = case.get("should_trigger_tavily", False)
        is_abstention = category in ("corpus_cannot_answer",)
        is_trap = category in ("hallucination_trap",)

        logger.info(f"[{idx}/{len(selected_test_cases)}] Evaluating [{category}]: '{query[:50]}'...")

        try:
            # 1. Evaluate Retrieval
            kb_candidates = retrieval_service.hybrid_search(db, query, top_k=settings.TOP_K)
            ret_metrics = retrieval_evaluator.evaluate(query, kb_candidates, keywords)
            recall_at_5_list.append(ret_metrics["recall_at_5"])
            context_precision_list.append(ret_metrics["context_precision"])
            context_recall_list.append(ret_metrics["context_recall"])

            # 2. Execute full RAG pipeline
            rag_resp = rag_service.process_query(db, query)

            # 3. Grounding & Technical Identifier Evaluation
            gr_metrics = grounding_evaluator.evaluate(
                rag_resp, is_abstention_case=is_abstention, is_hallucination_trap=is_trap
            )
            grounding_score_list.append(gr_metrics["answer_grounding_score"])
            tech_id_accuracy_list.append(gr_metrics["tech_identifier_accuracy"])
            abstention_quality_list.append(gr_metrics["abstention_quality"])

            # 4. Citation Correctness
            cit_metrics = citation_evaluator.evaluate(rag_resp)
            citation_correctness_list.append(cit_metrics["citation_correctness"])

            # 5. Follow-up Evaluation
            fo_metrics = followup_evaluator.evaluate(rag_resp)
            followup_relevance_list.append(fo_metrics["followup_relevance"])

            # 6. Tavily Trigger Accuracy
            actual_trigger = rag_resp.get("external_search_used", False)
            if should_trigger and actual_trigger:
                tavily_tp += 1
            elif not should_trigger and actual_trigger:
                tavily_fp += 1
            elif not should_trigger and not actual_trigger:
                tavily_tn += 1
            elif should_trigger and not actual_trigger:
                tavily_fn += 1

            # 7. Answer Sufficiency (passes verification or correctly refused)
            ans_len = len(rag_resp.get("answer", ""))
            sufficient = 1.0 if (gr_metrics["answer_grounding_score"] >= 0.80 or gr_metrics["abstention_quality"] == 1.0) and ans_len > 30 else 0.5
            sufficiency_list.append(sufficient)

            evaluated_cases.append({
                "id": case.get("id"),
                "category": category,
                "query": query,
                "grounding_score": gr_metrics["answer_grounding_score"],
                "verification_status": rag_resp.get("verification_status"),
                "source_type": rag_resp.get("source_type"),
                "external_search_used": actual_trigger,
                "recall_at_5": ret_metrics["recall_at_5"],
                "citation_correctness": cit_metrics["citation_correctness"],
                "follow_up_count": len(rag_resp.get("follow_up_questions", []))
            })

        except Exception as err:
            logger.error(f"Error evaluating '{query}': {err}", exc_info=True)

    db.close()

    # Calculate aggregate metrics
    avg = lambda lst: round(sum(lst) / len(lst), 4) if lst else 0.0

    tavily_precision = round(tavily_tp / (tavily_tp + tavily_fp), 4) if (tavily_tp + tavily_fp) > 0 else 1.0
    tavily_recall = round(tavily_tp / (tavily_tp + tavily_fn), 4) if (tavily_tp + tavily_fn) > 0 else 1.0

    final_metrics = {
        "1_Retrieval_Recall_at_5": avg(recall_at_5_list),
        "2_Context_Precision": avg(context_precision_list),
        "3_Context_Recall": avg(context_recall_list),
        "4_Answer_Grounding_Score": avg(grounding_score_list),
        "5_Citation_Correctness": avg(citation_correctness_list),
        "6_Technical_Identifier_Accuracy": avg(tech_id_accuracy_list),
        "7_Tavily_Trigger_Precision": tavily_precision,
        "7_Tavily_Trigger_Recall": tavily_recall,
        "8_Answer_Sufficiency": avg(sufficiency_list),
        "9_Followup_Question_Relevance": avg(followup_relevance_list),
        "10_Abstention_Quality": avg(abstention_quality_list),
        "total_evaluated_queries": len(selected_test_cases)
    }

    # Save to JSON
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"metrics": final_metrics, "cases": evaluated_cases}, f, indent=2)

    logger.info("Evaluation complete! Results:")
    for k, v in final_metrics.items():
        logger.info(f"  {k}: {v}")

    return final_metrics


if __name__ == "__main__":
    run_benchmark(sample_size=35)
