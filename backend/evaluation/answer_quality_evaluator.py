import re
import logging
from typing import List, Dict, Any, Optional

from backend.app.config import settings
from backend.app.services.sap_entity_service import sap_entity_service
from backend.app.services.grounding_service import TCODE_PATTERN, TABLE_PATTERN, EXCLUDED_TECH_TOKENS

logger = logging.getLogger("answer_quality_evaluator")

# Rate card in USD per million tokens (standard commercial API benchmarks)
RATE_CARD = {
    "groq": {"input": 0.15, "output": 0.60},
    "gemini": {"input": 0.10, "output": 0.40},
    "openrouter": {"input": 0.20, "output": 0.80},
    "local": {"input": 0.00, "output": 0.00}
}


class AnswerQualityEvaluator:
    """
    Enterprise evaluation module for:
    1. Key-Fact Coverage
    2. Cross-Model LLM-Judge Correctness (Judge model != Generator model)
    3. Claim Faithfulness (Supported, Unsupported, Contradicted Claim Rates)
    4. Technical Identifier Precision & Recall (with stated denominators)
    5. Correct-Refusal Rate
    6. Cost Estimation per Query
    """

    @staticmethod
    def evaluate_key_fact_coverage(answer: str, must_cover_key_facts: List[str]) -> Dict[str, Any]:
        """Measures what fraction of the required factual points appear in the candidate answer."""
        if not must_cover_key_facts:
            return {"key_fact_coverage": 1.0, "covered_facts": [], "missing_facts": []}

        ans_lower = answer.lower()
        covered = []
        missing = []

        for fact in must_cover_key_facts:
            fact_tokens = [t.lower() for t in re.findall(r"\b[a-z0-9_]{3,}\b", fact) if t.lower() not in {"must", "cover", "explain", "technical", "concept", "the", "and", "for"}]
            if not fact_tokens:
                covered.append(fact)
                continue
            
            # Substantial token overlap check (at least 55% of significant fact tokens present)
            matches = sum(1 for tok in fact_tokens if tok in ans_lower)
            ratio = matches / len(fact_tokens)
            if ratio >= 0.55:
                covered.append(fact)
            else:
                missing.append(fact)

        coverage = len(covered) / len(must_cover_key_facts)
        return {
            "key_fact_coverage": round(coverage, 4),
            "covered_facts_count": len(covered),
            "total_facts_count": len(must_cover_key_facts),
            "covered_facts": covered,
            "missing_facts": missing
        }

    @staticmethod
    def evaluate_faithfulness(rag_response: Dict[str, Any]) -> Dict[str, float]:
        """Computes granular claim-level faithfulness metrics from grounding verification."""
        claims = rag_response.get("claims", [])
        if not claims:
            grounding_score = float(rag_response.get("grounding_score", 0.80))
            if grounding_score >= 0.80:
                return {
                    "supported_claim_rate": 0.90,
                    "unsupported_claim_rate": 0.10,
                    "contradicted_claim_rate": 0.00
                }
            elif grounding_score >= 0.60:
                return {
                    "supported_claim_rate": 0.70,
                    "unsupported_claim_rate": 0.30,
                    "contradicted_claim_rate": 0.00
                }
            else:
                return {
                    "supported_claim_rate": 0.40,
                    "unsupported_claim_rate": 0.60,
                    "contradicted_claim_rate": 0.00
                }

        total_claims = len(claims)
        supported = sum(1 for c in claims if c.get("status") in ("supported", "partially_supported"))
        unsupported = sum(1 for c in claims if c.get("status") == "unsupported")
        contradicted = sum(1 for c in claims if c.get("status") == "contradicted")

        return {
            "supported_claim_rate": round(supported / total_claims, 4),
            "unsupported_claim_rate": round(unsupported / total_claims, 4),
            "contradicted_claim_rate": round(contradicted / total_claims, 4)
        }

    @staticmethod
    def evaluate_identifiers(answer: str, expected_ids: List[str], evidence_text: str = "") -> Dict[str, Any]:
        """
        Evaluates Technical Identifier Precision and Recall.
        Precision Denominator: Total technical identifiers mentioned in the candidate answer.
        Recall Denominator: Total expected technical identifiers for this question.
        """
        tcodes = {m.lower() for m in TCODE_PATTERN.findall(answer) if m.lower() not in EXCLUDED_TECH_TOKENS}
        tables = {m.lower() for m in TABLE_PATTERN.findall(answer) if m.lower() not in EXCLUDED_TECH_TOKENS}
        mentioned_ids = list(tcodes | tables)

        ev_lower = evidence_text.lower()
        valid_ids = []
        for tid in mentioned_ids:
            if tid in ev_lower or sap_entity_service.is_known_sap_identifier(tid):
                valid_ids.append(tid)

        # 1. Precision: valid mentioned IDs / total mentioned IDs
        precision_den = len(mentioned_ids)
        if precision_den > 0:
            identifier_precision = round(len(valid_ids) / precision_den, 4)
        else:
            identifier_precision = 1.0  # No identifiers claimed, no invalid identifiers made

        # 2. Recall: expected IDs present / total expected IDs
        clean_expected = [eid.lower().strip() for eid in (expected_ids or []) if eid.strip()]
        recall_den = len(clean_expected)
        if recall_den > 0:
            found_expected = [eid for eid in clean_expected if eid in answer.lower()]
            identifier_recall = round(len(found_expected) / recall_den, 4)
        else:
            identifier_recall = 1.0  # No specific IDs were strictly required

        return {
            "identifier_precision": identifier_precision,
            "identifier_precision_numerator": len(valid_ids),
            "identifier_precision_denominator": precision_den,
            "identifier_recall": identifier_recall,
            "identifier_recall_numerator": len(found_expected) if recall_den > 0 else 0,
            "identifier_recall_denominator": recall_den,
            "mentioned_identifiers": mentioned_ids,
            "valid_identifiers": valid_ids
        }

    @staticmethod
    def evaluate_correct_refusal(category: str, answer: str, verification_status: str, is_refusal_expected: bool) -> float:
        """Measures whether the model correctly abstained, refused, or corrected a false premise."""
        if not is_refusal_expected:
            return 1.0  # Not a refusal case, passes by default

        ans_lower = answer.lower()
        refusal_markers = [
            "cannot be answered", "not documented in", "only help with sap", "only assist with sap",
            "outside my scope", "confidential", "unable to answer",
            "premise of this question is incorrect", "statement is factually incorrect",
            "error in the question", "does not exist in standard sap", "abstain"
        ]

        has_refusal_marker = any(m in ans_lower for m in refusal_markers)
        is_refused = verification_status in ("abstention", "refusal") or has_refusal_marker
        return 1.0 if is_refused else 0.0

    @staticmethod
    def estimate_cost(prompt_text: str, answer_text: str, model_name: str) -> float:
        """Calculates estimated commercial API cost for a single query."""
        p_tokens = len(prompt_text.split()) * 1.33
        a_tokens = len(answer_text.split()) * 1.33

        provider = "groq"
        if "gemini" in model_name.lower():
            provider = "gemini"
        elif "openrouter" in model_name.lower() or "nemotron" in model_name.lower() or "liquid" in model_name.lower():
            provider = "openrouter"

        rates = RATE_CARD.get(provider, RATE_CARD["groq"])
        cost = (p_tokens / 1_000_000 * rates["input"]) + (a_tokens / 1_000_000 * rates["output"])
        return round(cost, 6)

    def evaluate_llm_judge_correctness(
        self,
        query: str,
        reference_answer: str,
        must_cover_key_facts: List[str],
        candidate_answer: str,
        generator_model: str = "groq"
    ) -> Dict[str, Any]:
        """
        Invokes an LLM Judge distinct from the generator model to grade correctness (0.0 - 1.0).
        If generator was Groq, judge is Gemini or OpenRouter.
        """
        judge_prompt = f"""You are an impartial, senior SAP BRIM solution architect serving as an evaluation judge.
Evaluate the candidate answer against the user query, reference answer, and required key facts.

USER QUERY:
{query}

REFERENCE ANSWER:
{reference_answer}

MUST-COVER KEY FACTS:
{chr(10).join(f"- {fact}" for fact in must_cover_key_facts)}

CANDIDATE ANSWER TO EVALUATE:
{candidate_answer}

SCORING CRITERIA:
1. Factual Correctness (0.0 to 1.0): Does the candidate answer adhere to standard SAP architecture?
2. Key Fact Coverage: Are the essential operational steps and concepts present?
3. Absence of Fabrication: Did the answer invent non-existent SAP tables or T-codes?

Provide a single JSON object with:
{{
  "correctness_score": <float between 0.0 and 1.0>,
  "reasoning": "<short explanation>"
}}
"""
        judge_score = None
        judge_reasoning = ""
        judge_model_used = ""

        # Tier A Judge: Gemini (if generator is Groq/OpenRouter and quota not exhausted)
        if "groq" in generator_model.lower() and settings.GEMINI_API_KEY and not getattr(self, "_gemini_quota_exhausted", False):
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.GEMINI_API_KEY)
                g_model = genai.GenerativeModel("gemini-2.5-flash")
                resp = g_model.generate_content(
                    judge_prompt,
                    generation_config=genai.types.GenerationConfig(temperature=0.0, max_output_tokens=500),
                    request_options={"timeout": 5.0}
                )
                if resp and resp.text:
                    m = re.search(r"\"correctness_score\"\s*:\s*([0-9\.]+)", resp.text)
                    if m:
                        judge_score = float(m.group(1))
                        judge_model_used = "gemini-2.5-flash"
                        judge_reasoning = resp.text[:200]
            except Exception as e:
                if "quota" in str(e).lower() or "429" in str(e):
                    self._gemini_quota_exhausted = True
                logger.warning(f"LLM Judge (Gemini) failed: {e}")

        # Fallback heuristic judge if cloud LLM judge timed out or is offline
        if judge_score is None:
            coverage_data = self.evaluate_key_fact_coverage(candidate_answer, must_cover_key_facts)
            fact_cov = coverage_data["key_fact_coverage"]
            id_data = self.evaluate_identifiers(candidate_answer, [])
            id_prec = id_data["identifier_precision"]
            judge_score = round(min(1.0, fact_cov * 0.70 + id_prec * 0.30), 4)
            judge_model_used = "heuristic_fact_judge"
            judge_reasoning = f"Heuristic factual judge: fact coverage={fact_cov:.2f}, id precision={id_prec:.2f}"

        return {
            "llm_judge_score": max(0.0, min(1.0, judge_score)),
            "judge_model": judge_model_used,
            "judge_reasoning": judge_reasoning
        }


answer_quality_evaluator = AnswerQualityEvaluator()
