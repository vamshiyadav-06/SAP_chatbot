import os
import re
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from backend.app.config import settings
from backend.app.schemas.grounded_generation import (
    GroundedAnswerResponse,
    GroundedClaim,
    ContextPackingResult
)

logger = logging.getLogger(__name__)


class GroundedGeneratorService:
    """
    Step 1 Generation Contract Service with User Corrections:
    - Statuses: ok, abstained_insufficient_context, generation_error, rate_limited
    - Exponential backoff for HTTP 429 rate limits
    - Reasoning text stripper (<think>...</think> and preambles) before JSON parsing
    - Computes modules_covered strictly from cited chunks' module tags (not model self-report)
    - If only some modules lack coverage, generates partial answer with gaps instead of abstaining
    """

    def __init__(self):
        self.fixed_model = getattr(settings, "GROUNDED_GENERATOR_MODEL", "qwen/qwen3.8-27b")
        self.temperature = min(float(getattr(settings, "GROUNDED_TEMPERATURE", 0.15)), 0.20)
        self.prompt_path = Path(getattr(settings, "PROMPT_PATH_GROUNDED_ANSWER", Path(__file__).parent.parent / "prompts" / "grounded_answer.txt"))
        self._system_prompt_cache: Optional[str] = None
        self.max_rate_limit_retries = getattr(settings, "RATE_LIMIT_MAX_RETRIES", 3)
        self.base_backoff_sec = getattr(settings, "RATE_LIMIT_BASE_BACKOFF_SEC", 2.0)

    def load_system_prompt(self) -> str:
        """Loads runtime system prompt from configured path."""
        if self._system_prompt_cache:
            return self._system_prompt_cache

        if self.prompt_path.exists():
            try:
                content = self.prompt_path.read_text(encoding="utf-8").strip()
                if content:
                    self._system_prompt_cache = content
                    return content
            except Exception as e:
                logger.warning(f"Failed to read system prompt from {self.prompt_path}: {e}")

        fallback = (
            "You are Clyptus.AI. Output strictly valid JSON matching the schema with summary, sections, "
            "claims (citations, identifiers_used, module, support), calculations, premise_correction, gaps, and next_questions."
        )
        self._system_prompt_cache = fallback
        return fallback

    @staticmethod
    def strip_reasoning_and_preamble(raw_text: str) -> str:
        """
        Strips reasoning blocks (<think>...</think>, [THINKING]...[/THINKING], or markdown fences)
        and extracts strictly the JSON body.
        """
        cleaned = raw_text.strip()
        # 1. Strip <think> tags (common in reasoning models)
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE).strip()
        # 2. Strip [THINKING] tags
        cleaned = re.sub(r"\[THINKING\][\s\S]*?\[/THINKING\]", "", cleaned, flags=re.IGNORECASE).strip()
        # 3. Strip markdown code fences
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        # 4. Extract text between first { and last }
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]

        return cleaned

    def _call_fixed_generator_with_backoff(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Executes call with exponential backoff on 429 rate limit errors.
        Returns: (raw_content, error_status)
        """
        groq_key = getattr(settings, "GROQ_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
        openrouter_key = (
            getattr(settings, "OPENROUTER_API_KEY", "")
            or getattr(settings, "LLM_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY", "")
        )

        for attempt in range(self.max_rate_limit_retries + 1):
            try:
                # 1. Groq Client
                if groq_key:
                    from groq import Groq
                    client = Groq(api_key=groq_key.strip(), timeout=16.0, max_retries=0)
                    response = client.chat.completions.create(
                        model=self.fixed_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        response_format={"type": "json_object"},
                        max_tokens=4096,
                        timeout=30.0
                    )
                    if response.choices and response.choices[0].message and response.choices[0].message.content:
                        return response.choices[0].message.content.strip(), None

                # 2. OpenRouter Client
                elif openrouter_key:
                    import requests
                    headers = {
                        "Authorization": f"Bearer {openrouter_key.strip()}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": self.fixed_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                        "max_tokens": 4096
                    }
                    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
                    if r.status_code == 200:
                        data = r.json()
                        choices = data.get("choices", [])
                        if choices and choices[0].get("message", {}).get("content"):
                            return choices[0]["message"]["content"].strip(), None
                    elif r.status_code == 429:
                        raise Exception(f"HTTP 429 Rate Limit: {r.text}")
                    else:
                        raise Exception(f"OpenRouter error {r.status_code}: {r.text}")

                else:
                    # Mock / Local deterministic generation when external keys absent
                    logger.warning("[GroundedGenerator] External LLM keys unavailable. Generating local structured output.")
                    return json.dumps({
                        "summary": "External live API offline.",
                        "sections": [],
                        "claims": [],
                        "calculations": [],
                        "premise_correction": None,
                        "gaps": ["Live LLM keys offline"],
                        "next_questions": [],
                        "is_abstention": True,
                        "abstention_reason": "No live LLM credentials configured."
                    }), None

            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = ("429" in err_str or "rate limit" in err_str or "quota" in err_str)
                if is_rate_limit and attempt < self.max_rate_limit_retries:
                    # Parse specific retry wait seconds from provider message if provided
                    wait_match = re.search(r"try again in (\d+\.?\d*)s", err_str)
                    if wait_match:
                        wait_sec = float(wait_match.group(1)) + 1.5
                    else:
                        wait_sec = self.base_backoff_sec * (2 ** attempt)
                    logger.warning(f"[RateLimit 429] Backing off {wait_sec:.1f}s (attempt {attempt+1}/{self.max_rate_limit_retries})...")
                    time.sleep(wait_sec)
                    continue
                elif is_rate_limit:
                    logger.error(f"[RateLimit 429] Retries exhausted: {e}")
                    return None, "rate_limited"
                else:
                    logger.error(f"[GroundedGenerator] Call error: {e}")
                    return None, "generation_error"

        return None, "generation_error"

    def _parse_and_validate(self, raw_text: str) -> GroundedAnswerResponse:
        """Strips reasoning text and validates JSON with Pydantic."""
        cleaned = self.strip_reasoning_and_preamble(raw_text)
        data = json.loads(cleaned)
        return GroundedAnswerResponse.model_validate(data)

    @staticmethod
    def compute_modules_covered(
        claims: List[GroundedClaim],
        packing_result: ContextPackingResult
    ) -> List[str]:
        """
        Computes modules_covered strictly from cited chunks' module tags
        (does NOT rely on model self-report).
        """
        chunk_map = {c.chunk_id: c.module for c in packing_result.packed_chunks}
        modules = set()
        for cl in claims:
            for cid in cl.citations:
                if cid in chunk_map and chunk_map[cid] != "General":
                    modules.add(chunk_map[cid])
        return sorted(list(modules))

    def generate_grounded_answer(
        self,
        query: str,
        packing_result: ContextPackingResult
    ) -> Dict[str, Any]:
        """
        Executes full generation contract:
        - If packing reports insufficient knowledge across all required concepts -> abstained_insufficient_context
        - Partial answer generation with gaps when some modules are covered
        - Handles 429 rate limit backoff -> rate_limited
        - Single retry on schema error -> generation_error on persistent failure
        - Returns status: ok, abstained_insufficient_context, generation_error, rate_limited
        """
        start_time = time.time()

        # Step 2 Gate: Insufficient knowledge check across entire question
        if packing_result.is_insufficient:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            safe_abstention = GroundedAnswerResponse(
                summary="Insufficient enterprise documentation to ground a verified response.",
                sections=[],
                claims=[],
                calculations=[],
                premise_correction=None,
                gaps=packing_result.detected_question_modules or ["Requested technical detail"],
                next_questions=[],
                is_abstention=True,
                abstention_reason="Insufficient knowledge in enterprise documentation (retrieval score below calibrated threshold)."
            )
            return {
                "answer_response": safe_abstention,
                "raw_json": safe_abstention.model_dump_json(indent=2),
                "retry_count": 0,
                "model_used": self.fixed_model,
                "temperature": self.temperature,
                "status": "abstained_insufficient_context",
                "latency_ms": latency_ms,
                "token_count": len(safe_abstention.model_dump_json().split()),
                "computed_modules_covered": [],
                "closest_sources": packing_result.closest_sources
            }

        system_prompt = self.load_system_prompt()
        user_prompt = (
            f"USER INQUIRY:\n{query}\n\n"
            f"CONTEXT CHUNKS:\n{packing_result.packed_text}\n\n"
            f"Provide your grounded JSON response now conforming strictly to the schema."
        )

        # Call fixed generator with 429 backoff
        raw_output, call_status = self._call_fixed_generator_with_backoff(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=self.temperature
        )

        if call_status == "rate_limited":
            latency_ms = round((time.time() - start_time) * 1000, 2)
            abstention = GroundedAnswerResponse(
                summary="Generation temporarily rate limited by model provider.",
                sections=[],
                claims=[],
                calculations=[],
                premise_correction=None,
                gaps=["Model provider rate limit encountered."],
                next_questions=[],
                is_abstention=True,
                abstention_reason="Rate limit encountered (HTTP 429) across all backoff attempts."
            )
            return {
                "answer_response": abstention,
                "raw_json": abstention.model_dump_json(indent=2),
                "retry_count": self.max_rate_limit_retries,
                "model_used": self.fixed_model,
                "temperature": self.temperature,
                "status": "rate_limited",
                "latency_ms": latency_ms,
                "token_count": len(abstention.model_dump_json().split()),
                "computed_modules_covered": [],
                "closest_sources": packing_result.closest_sources
            }

        if not raw_output:
            latency_ms = round((time.time() - start_time) * 1000, 2)
            abstention = GroundedAnswerResponse(
                summary="Technical generation error occurred.",
                sections=[],
                claims=[],
                calculations=[],
                premise_correction=None,
                gaps=["Failed to generate response."],
                next_questions=[],
                is_abstention=True,
                abstention_reason="Empty response or provider failure."
            )
            return {
                "answer_response": abstention,
                "raw_json": abstention.model_dump_json(indent=2),
                "retry_count": 0,
                "model_used": self.fixed_model,
                "temperature": self.temperature,
                "status": "generation_error",
                "latency_ms": latency_ms,
                "token_count": len(abstention.model_dump_json().split()),
                "computed_modules_covered": [],
                "closest_sources": packing_result.closest_sources
            }

        # Attempt 1: Parse and validate JSON
        try:
            validated = self._parse_and_validate(raw_output)

            # Auto-populate uncovered modules into gaps if only some modules lack coverage
            if packing_result.uncovered_question_modules:
                for unc_mod in packing_result.uncovered_question_modules:
                    gap_msg = f"Module {unc_mod} lacked supporting documentation in the retrieved context."
                    if gap_msg not in validated.gaps:
                        validated.gaps.append(gap_msg)

            computed_modules = self.compute_modules_covered(validated.claims, packing_result)
            latency_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "answer_response": validated,
                "raw_json": raw_output,
                "retry_count": 0,
                "model_used": self.fixed_model,
                "temperature": self.temperature,
                "status": "ok",
                "latency_ms": latency_ms,
                "token_count": len(raw_output.split()),
                "computed_modules_covered": computed_modules,
                "closest_sources": packing_result.closest_sources
            }

        except Exception as first_err:
            logger.warning(f"First JSON parse attempt failed: {first_err}. Attempting single retry with error feedback.")

            # Single retry with explicit feedback
            retry_prompt = (
                f"{user_prompt}\n\n"
                f"[ERROR ON PREVIOUS ATTEMPT]: {str(first_err)}\n"
                f"Your previous output was:\n{raw_output[:500]}\n\n"
                f"CORRECTION: Return ONLY the raw valid JSON object adhering strictly to the schema."
            )

            retry_output, retry_call_status = self._call_fixed_generator_with_backoff(
                prompt=retry_prompt,
                system_prompt=system_prompt,
                temperature=self.temperature
            )

            if retry_output:
                try:
                    validated = self._parse_and_validate(retry_output)
                    if packing_result.uncovered_question_modules:
                        for unc_mod in packing_result.uncovered_question_modules:
                            gap_msg = f"Module {unc_mod} lacked supporting documentation in the retrieved context."
                            if gap_msg not in validated.gaps:
                                validated.gaps.append(gap_msg)

                    computed_modules = self.compute_modules_covered(validated.claims, packing_result)
                    latency_ms = round((time.time() - start_time) * 1000, 2)

                    return {
                        "answer_response": validated,
                        "raw_json": retry_output,
                        "retry_count": 1,
                        "model_used": self.fixed_model,
                        "temperature": self.temperature,
                        "status": "ok",
                        "latency_ms": latency_ms,
                        "token_count": len(retry_output.split()),
                        "computed_modules_covered": computed_modules,
                        "closest_sources": packing_result.closest_sources
                    }
                except Exception as second_err:
                    logger.error(f"Retry JSON parse failed: {second_err}. Returning generation_error.")

            latency_ms = round((time.time() - start_time) * 1000, 2)
            safe_abstention = GroundedAnswerResponse(
                summary="Generation failed validation after retry.",
                sections=[],
                claims=[],
                calculations=[],
                premise_correction=None,
                gaps=[query],
                next_questions=[],
                is_abstention=True,
                abstention_reason=f"Safe abstention: JSON schema validation failed ({str(first_err)[:80]})."
            )
            return {
                "answer_response": safe_abstention,
                "raw_json": safe_abstention.model_dump_json(indent=2),
                "retry_count": 1,
                "model_used": self.fixed_model,
                "temperature": self.temperature,
                "status": "generation_error",
                "latency_ms": latency_ms,
                "token_count": len(safe_abstention.model_dump_json().split()),
                "computed_modules_covered": [],
                "closest_sources": packing_result.closest_sources
            }


grounded_generator_service = GroundedGeneratorService()
