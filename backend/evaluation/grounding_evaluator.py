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
                or "only assist with sap" in answer.lower()
            )
            abstention_quality = 1.0 if is_refusal else 0.0
        else:
            abstention_quality = 1.0  # Not an abstention case

        # 2. Technical Identifier Accuracy
        # High-precision pattern matching true SAP transactions, tables, and customizing views
        TECH_EVAL_PATTERN = re.compile(
            r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|fkkbix_[a-z0-9_]+|fkkbi_[a-z0-9_]+|fkk[a-z0-9_]+|"
            r"fp[a-z0-9_]{2,8}|crmd_[a-z0-9_]+|farr_[a-z0-9_]+|wty_[a-z0-9_]+|"
            r"dfkk[a-z0-9_]+|erdk|erch|but0[0-9]{2}|but0bk|mara|marc|vbak|vbap|ekko|ekpo|bseg|bkpf|v_fkk[a-z0-9_]+|"
            r"me[0-9]{2}[a-z]?|va[0-9]{2}|vf[0-9]{2}|vk[0-9]{2}|fb[0-9]{2}|f110|"
            r"se[0-9]{2}[a-z]?|sm[0-9]{2}|st[0-9]{2}|slg[0-9]|spro|swo1|sicf|miro|migo)\b",
            re.IGNORECASE
        )
        EXCLUDED_EVAL_TOKENS = {
            "b2b", "b2c", "p10", "p50", "p90", "p95", "p99", "v1", "v2", "v3", "ed1",
            "2nd", "1st", "3rd", "sap", "som", "cc", "ci", "fica", "rar", "crm", "ecc",
            "gui", "iot", "api", "erp", "rfc", "tcp", "ssl", "http", "rest", "soap",
            "json", "xml", "csv", "sql", "hana", "btp", "cdr", "bit", "cit", "sla",
            "e2e", "q1", "q2", "q3", "q4", "24x7", "2020", "1909", "404", "500", "100",
            "http400", "http500", "http200", "the", "and", "for", "with"
        }

        raw_ids = [m.group(0).lower() for m in TECH_EVAL_PATTERN.finditer(answer)]
        filtered_ids = [tid for tid in raw_ids if len(tid) >= 3 and tid not in EXCLUDED_EVAL_TOKENS]

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
