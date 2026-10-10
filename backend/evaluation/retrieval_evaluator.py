import re
from typing import List, Dict, Any

class RetrievalEvaluator:
    """Evaluates retrieval performance: Recall@5, Context Precision, and Context Recall."""

    @staticmethod
    def evaluate(query: str, retrieved_chunks: List[Dict[str, Any]], expected_keywords: List[str]) -> Dict[str, float]:
        if not expected_keywords:
            return {"recall_at_5": 1.0, "context_precision": 1.0, "context_recall": 1.0}

        if not retrieved_chunks:
            return {"recall_at_5": 0.0, "context_precision": 0.0, "context_recall": 0.0}

        top_5 = retrieved_chunks[:5]
        top_5_text = " ".join((c.get("chunk_text") or c.get("snippet") or "").lower() for c in top_5)
        all_text = " ".join((c.get("chunk_text") or c.get("snippet") or "").lower() for c in retrieved_chunks)

        # 1. Recall@5: Fraction of expected keywords found in top 5 chunks
        matched_in_top5 = sum(1 for kw in expected_keywords if kw.lower() in top_5_text)
        recall_at_5 = matched_in_top5 / len(expected_keywords)

        # 2. Context Recall: Fraction of expected keywords found across all retrieved chunks
        matched_total = sum(1 for kw in expected_keywords if kw.lower() in all_text)
        context_recall = matched_total / len(expected_keywords)

        # 3. Context Precision: Fraction of top-5 chunks containing at least one query/expected keyword
        relevant_chunks_in_top5 = 0
        for c in top_5:
            c_text = (c.get("chunk_text") or c.get("snippet") or "").lower()
            if any(kw.lower() in c_text for kw in expected_keywords):
                relevant_chunks_in_top5 += 1
        context_precision = relevant_chunks_in_top5 / len(top_5) if top_5 else 0.0

        return {
            "recall_at_5": round(recall_at_5, 4),
            "context_precision": round(context_precision, 4),
            "context_recall": round(context_recall, 4)
        }

retrieval_evaluator = RetrievalEvaluator()
