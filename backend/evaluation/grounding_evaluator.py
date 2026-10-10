import re
from typing import List, Dict, Any

from backend.app.services.sap_entity_service import sap_entity_service

class GroundingEvaluator:
    """Evaluates Grounding Score, Technical Identifier Accuracy, and Abstention Quality."""

    @staticmethod
    def evaluate(
        rag_response: Dict[str, Any],
        is_abstention_case: bool = False,
        is_hallucination_trap: bool = False
    ) -> Dict[str, float]:
        answer = rag_response.get("answer", "")
        grounding_score = float(rag_response.get("grounding_score", 0.0))
        verification_status = rag_response.get("verification_status", "unverified")

        # 1. Abstention Quality
        if is_abstention_case or is_hallucination_trap:
            # Did the model correctly abstain or identify limitation instead of fabricating?
            is_refusal = (
                verification_status == "abstention"
                or "unable to" in answer.lower()
                or "does not exist" in answer.lower()
                or "not standard" in answer.lower()
                or "could not be verified" in answer.lower()
                or "insufficient" in answer.lower()
                or "only help with sap" in answer.lower()
            )
            abstention_quality = 1.0 if is_refusal else 0.0
        else:
            abstention_quality = 1.0  # Not an abstention case

        # 2. Technical Identifier Accuracy
        # Extract T-Codes and table names mentioned in answer
        mentioned_ids = re.findall(r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|[a-z]{1,2}[0-9]{2}[a-z0-9]?|dfkk[a-z0-9_]+)\b", answer.lower())
        filtered_ids = [tid for tid in mentioned_ids if len(tid) >= 3 and tid not in {"the", "and", "for", "with"}]

        if filtered_ids:
            # Check if each mentioned ID was either in evidence or in known SAP entity registry
            evidence_text = " ".join(
                c.get("snippet", "") + " " + c.get("document", "")
                for c in rag_response.get("citations", [])
            ).lower()

            valid_count = 0
            for tid in filtered_ids:
                if tid in evidence_text or sap_entity_service.is_known_sap_identifier(tid):
                    valid_count += 1
            tech_id_accuracy = valid_count / len(filtered_ids)
        else:
            tech_id_accuracy = 1.0

        return {
            "answer_grounding_score": round(grounding_score, 4),
            "tech_identifier_accuracy": round(tech_id_accuracy, 4),
            "abstention_quality": round(abstention_quality, 4)
        }

grounding_evaluator = GroundingEvaluator()
