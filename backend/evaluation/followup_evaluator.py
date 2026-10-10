from typing import List, Dict, Any

class FollowupEvaluator:
    """Evaluates Recommended Follow-up Questions: exactly 3 questions, relevance, distinctness."""

    @staticmethod
    def evaluate(rag_response: Dict[str, Any]) -> Dict[str, float]:
        follow_ups = rag_response.get("follow_up_questions", [])
        source_type = rag_response.get("source_type", "")

        if source_type in ("refusal", "error"):
            return {"followup_count_accuracy": 1.0, "followup_relevance": 1.0}

        # Check count
        count_accuracy = 1.0 if len(follow_ups) == 3 else (len(follow_ups) / 3.0)

        # Check distinctness, length, and punctuation
        distinct = len(set(q.lower().strip() for q in follow_ups))
        valid_questions = 0
        for q in follow_ups:
            if len(q.strip()) > 10 and q.strip().endswith("?"):
                valid_questions += 1

        relevance = (valid_questions / len(follow_ups)) * (distinct / len(follow_ups)) if follow_ups else 0.0

        return {
            "followup_count_accuracy": round(count_accuracy, 4),
            "followup_relevance": round(relevance, 4)
        }

followup_evaluator = FollowupEvaluator()
