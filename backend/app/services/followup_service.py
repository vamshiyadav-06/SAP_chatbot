import json
import re
import logging
from typing import List, Dict, Any, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)


class FollowupService:
    """
    Recommended Follow-Up Questions Service for SAP BRIM Knowledge Assistant.
    
    Generates exactly three distinct, technically relevant, one-click clickable questions:
    - Anchored in verified response content and adjacent SAP BRIM topics
    - Avoids assuming unsupported facts
    - Validates count, non-emptiness, and distinctness
    """

    def __init__(self):
        self.question_count = settings.FOLLOWUP_QUESTION_COUNT

    @staticmethod
    def _clean_question(q: str) -> str:
        """Cleans bullet markers, quotes, and whitespace from a candidate follow-up question."""
        cleaned = re.sub(r"^[\d\.\-\*\s]+", "", q).strip()
        cleaned = re.sub(r"^[\"']|[\"']$", "", cleaned).strip()
        if cleaned and not cleaned.endswith("?"):
            cleaned += "?"
        return cleaned

    def generate_deterministic_followups(
        self,
        query: str,
        answer: str,
        selected_evidence: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generates robust, technically accurate follow-up questions tailored to SAP BRIM topics
        when LLM is offline or generates malformed output.
        """
        q_lower = query.lower()
        ans_lower = answer.lower()

        # Topic 1: Convergent Invoicing (CI) & Billable Items
        if any(term in q_lower or term in ans_lower for term in ["convergent invoicing", "ci", "billable item", "bit", "billing"]):
            return [
                "How does Convergent Invoicing process and aggregate raw billable items (BITs)?",
                "How does Convergent Invoicing post billing and invoice documents to FI-CA?",
                "Which standard monitor or transaction is used to investigate failed billing orders in CI?"
            ]

        # Topic 2: Convergent Charging (CC) & Rating
        if any(term in q_lower or term in ans_lower for term in ["convergent charging", "cc", "charging", "rating", "charge plan"]):
            return [
                "How are charge plans and pricing logic mapped to subscription contracts?",
                "What is the difference between online charging and offline batch rating in SAP CC?",
                "How do consumption items (CITs) flow from mediation into SAP Convergent Charging?"
            ]

        # Topic 3: Subscription Order Management (SOM)
        if any(term in q_lower or term in ans_lower for term in ["som", "subscription order", "provider order", "provider contract"]):
            return [
                "How does a provider order transition into an active provider contract in SOM?",
                "How are subscription allowances and recurring charges synchronized with SAP CC?",
                "What master data prerequisites are required in SAP SOM before order submission?"
            ]

        # Topic 4: FI-CA (Contract Accounts Receivable and Payable)
        if any(term in q_lower or term in ans_lower for term in ["fi-ca", "fica", "contract account", "clearing", "open item"]):
            return [
                "How does the FI-CA automatic clearing program process open receivables?",
                "How are payment runs (F110 / FP05) configured for high-volume customer accounts?",
                "What is the relationship between the Business Partner and the Contract Account in FI-CA?"
            ]

        # Topic 5: Configuration / SPRO
        if any(term in q_lower or term in ans_lower for term in ["configure", "configuration", "spro", "customizing"]):
            return [
                "What are the documented prerequisites before executing this configuration step?",
                "Which validation checks or test cases verify that this customizing is active?",
                "Are there specific release dependencies between SAP ECC and SAP S/4HANA for this setting?"
            ]

        # Topic 6: Troubleshooting / Errors
        if any(term in q_lower or term in ans_lower for term in ["error", "troubleshoot", "failed", "exception"]):
            return [
                "Which standard application log (SLG1) object records detailed diagnostic entries for this error?",
                "What evidence-supported corrective steps resolve this processing failure?",
                "How can the transaction be safely re-executed after correcting the root cause?"
            ]

        # General Default SAP BRIM Questions
        return [
            "How does this component interact with Contract Accounts Receivable and Payable (FI-CA)?",
            "What master data and configuration prerequisites are documented for this process?",
            "Which monitoring transactions or diagnostic steps validate successful execution?"
        ]

    def generate_followup_questions(
        self,
        query: str,
        answer: str,
        selected_evidence: List[Dict[str, Any]],
        llm_generate_fn: Optional[Any] = None
    ) -> List[str]:
        """
        Generates exactly three distinct, relevant follow-up questions.
        Uses LLM prompt if available, with immediate validation and deterministic fallback.
        """
        # If no LLM generator or offline mode, use deterministic generator
        if not llm_generate_fn:
            return self.generate_deterministic_followups(query, answer, selected_evidence)[:self.question_count]

        prompt = (
            f"You are an SAP BRIM specialist. Based on the user's question and the verified answer below, "
            f"recommend exactly 3 relevant, highly technical, clickable follow-up questions.\n\n"
            f"User Question: {query}\n\n"
            f"Verified Answer (excerpt): {answer[:800]}\n\n"
            f"Requirements:\n"
            f"- Return JSON list of exactly 3 distinct strings: [\"Question 1?\", \"Question 2?\", \"Question 3?\"]\n"
            f"- Do NOT assume unverified facts or invent non-existent SAP products.\n"
            f"- Ensure each question is relevant, concise, and ends with a question mark.\n"
            f"- Output ONLY the valid JSON list."
        )

        try:
            raw_response = llm_generate_fn(prompt)
            # Parse JSON
            match = re.search(r"\[.*\]", raw_response, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                cleaned_list = []
                seen = set()
                for item in parsed:
                    if isinstance(item, str):
                        cq = self._clean_question(item)
                        if cq and cq.lower() not in seen and len(cq) > 10:
                            seen.add(cq.lower())
                            cleaned_list.append(cq)

                if len(cleaned_list) == self.question_count:
                    return cleaned_list
                elif len(cleaned_list) > self.question_count:
                    return cleaned_list[:self.question_count]
        except Exception as e:
            logger.warning(f"LLM follow-up generation failed: {e}. Using deterministic fallback.")

        # Fallback to guaranteed valid 3 questions
        return self.generate_deterministic_followups(query, answer, selected_evidence)[:self.question_count]


followup_service = FollowupService()
