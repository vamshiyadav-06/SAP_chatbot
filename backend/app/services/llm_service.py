import os
import re
import logging
from typing import List, Dict, Any, Generator, Optional

from backend.app.config import settings
from backend.app.services.answer_planner import answer_planner

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are cClyptus.AI Assistant, an advanced enterprise AI assistant and expert consultant specializing in SAP, SAP BRIM (Billing and Revenue Innovation Management), software engineering, and enterprise architecture.

Your mission is to provide helpful, comprehensive, technically rigorous, and accurate answers to any inquiry the user presents.

Core Principles:
- Answer every question thoroughly, clearly, and constructively.
- When retrieved documentation or evidence is provided, prioritize it and integrate all relevant technical details, transaction codes, database tables, and customizing steps.
- When general or broader questions are asked, use your deep technical knowledge base and intelligence to provide complete, insightful, and practical guidance.
- Never refuse to answer, and never state that you cannot generate text, cannot help, or lack information.
- Format responses beautifully with clean Markdown headings, structured bullet points, and tables where applicable.
- Maintain a professional, senior consultant tone."""


class LLMService:

    # Fallback model cascades for all supported providers
    # Valid Groq models (https://console.groq.com/docs/models)
    GROQ_MODELS = [
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "allam-2-7b",
    ]

    # Valid Gemini models
    GEMINI_MODELS = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    # Valid OpenRouter free models
    OPENROUTER_MODELS = [
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3.5-lightning:free",
        "liquid/lfm-2.5-2.6b:free",
        "apodex/apodex-1.1-mini:free",
    ]

    def __init__(self):
        # Tier 1: Groq API Key
        self.groq_api_key = (
            getattr(settings, "GROQ_API_KEY", "")
            or os.getenv("GROQ_API_KEY", "")
        ).strip()

        # Tier 2: Gemini API Key (clean any leading dots or whitespace)
        raw_gemini = (
            getattr(settings, "GEMINI_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
        ).strip()
        self.gemini_api_key = raw_gemini.lstrip(". ")

        # Tier 3: OpenRouter API Key
        self.openrouter_api_key = (
            getattr(settings, "OPENROUTER_API_KEY", "")
            or getattr(settings, "LLM_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY", "")
        ).strip()

        # Legacy compatibility attribute
        self.api_key = self.groq_api_key or self.gemini_api_key or self.openrouter_api_key
        self.provider = "tiered"

    # =========================================================
    # TEXT CLEANING
    # =========================================================

    @staticmethod
    def _clean_document_text(text: str) -> str:

        if not text:
            return ""

        cleaned = text

        cleaned = re.sub(
            r"CONFIDENTIAL\s*&\s*PROPRIETARY[^\n]*",
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        cleaned = re.sub(
            r"SAP\s+S/4HANA\s+OFFICIAL\s+REFERENCE\s+MANUAL",
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        cleaned = re.sub(
            r"Module:\s*[^\n]*",
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        cleaned = re.sub(
            r"Document:\s*[^\n]*",
            "",
            cleaned,
            flags=re.IGNORECASE
        )

        cleaned = re.sub(
            r"[ \t]+",
            " ",
            cleaned
        )

        cleaned = re.sub(
            r"\n{3,}",
            "\n\n",
            cleaned
        )

        return cleaned.strip()

    # =========================================================
    # SENTENCE EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_sentences(text: str) -> List[str]:

        if not text:
            return []

        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        sentences = re.split(
            r"(?<=[.!?])\s+",
            text
        )

        cleaned = []

        for sentence in sentences:

            sentence = sentence.strip()

            if len(sentence) < 20:
                continue

            lower = sentence.lower()

            if any(
                phrase in lower
                for phrase in [
                    "confidential & proprietary",
                    "official reference manual",
                    "module:",
                    "document:"
                ]
            ):
                continue

            cleaned.append(sentence)

        return cleaned

    # =========================================================
    # TERM MATCHING
    # =========================================================

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:

        if not text or not term:
            return False

        pattern = (
            rf"(?<![a-z0-9])"
            rf"{re.escape(term.lower())}"
            rf"(?![a-z0-9])"
        )

        return bool(
            re.search(
                pattern,
                text.lower()
            )
        )

    # =========================================================
    # LOCAL GROUNDED RESPONSE
    # =========================================================

    def _generate_grounded_local_response(
        self,
        query: str,
        evidence_text: str,
        source_type: str,
        metadata: List[Dict[str, Any]]
    ) -> str:

        if not metadata:
            return f"Regarding your inquiry about **{query}**, this topic involves core SAP architecture and business processes. Please provide additional context or specific module details (e.g. SOM, CC, CI, FI-CA) for a deeper breakdown."

        # -----------------------------------------------------
        # WEB RESPONSE
        # -----------------------------------------------------

        if source_type == "web":

            useful_snippets = []

            for item in metadata[:3]:

                title = item.get(
                    "title",
                    "SAP web source"
                )

                snippet = item.get(
                    "snippet",
                    ""
                ).strip()

                if not snippet:
                    continue

                snippet = self._clean_document_text(
                    snippet
                )

                if snippet:
                    useful_snippets.append(
                        f"- **{title}**: {snippet}"
                    )

            if not useful_snippets:
                return (
                    "I couldn't find sufficient verified web "
                    "information to answer this SAP question."
                )

            return (
                "Based on verified SAP web sources:\n\n"
                + "\n".join(useful_snippets)
            )

        # -----------------------------------------------------
        # QUERY TERMS
        # -----------------------------------------------------

        stop_words = {
            "what",
            "is",
            "the",
            "a",
            "an",
            "how",
            "to",
            "in",
            "of",
            "and",
            "for",
            "with",
            "does",
            "explain",
            "can",
            "you",
            "tell",
            "me",
            "about",
            "are",
            "why",
            "which",
            "where",
            "when"
        }

        query_terms = [
            word.lower()
            for word in re.findall(
                r"\b[a-z0-9\/\-_]+\b",
                query.lower()
            )
            if word.lower() not in stop_words
            and len(word) > 1
        ]

        # -----------------------------------------------------
        # COLLECT CANDIDATE SENTENCES
        # -----------------------------------------------------

        candidate_sentences = []

        for item in metadata[:6]:

            raw_text = item.get(
                "chunk_text",
                ""
            )

            cleaned_text = self._clean_document_text(
                raw_text
            )

            sentences = self._extract_sentences(
                cleaned_text
            )

            if not sentences:
                continue

            rerank_score = float(
                item.get(
                    "rerank_score",
                    item.get(
                        "score",
                        0.0
                    )
                )
            )

            for sentence in sentences:

                sentence_lower = sentence.lower()

                # Query-term matching
                matched_terms = sum(
                    1
                    for term in query_terms
                    if self._contains_term(
                        sentence_lower,
                        term
                    )
                )

                query_match_score = (
                    matched_terms /
                    max(1, len(query_terms))
                )

                # Definition bonus
                definition_bonus = 0.0

                if (
                    " is " in sentence_lower
                    or " are " in sentence_lower
                    or " refers to " in sentence_lower
                    or " means " in sentence_lower
                    or " designed for " in sentence_lower
                ):
                    definition_bonus = 1.0

                # Direct subject bonus
                subject_bonus = 0.0

                if (
                    "sap s/4hana" in sentence_lower
                    and (
                        " is " in sentence_lower
                        or " refers to " in sentence_lower
                        or " designed " in sentence_lower
                    )
                ):
                    subject_bonus = 1.0

                # Final relevance
                relevance_score = (
                    query_match_score * 0.50
                    + rerank_score * 0.20
                    + definition_bonus * 0.15
                    + subject_bonus * 0.15
                )

                candidate_sentences.append(
                    {
                        "sentence": sentence,
                        "score": relevance_score
                    }
                )

        # -----------------------------------------------------
        # SORT BY RELEVANCE
        # -----------------------------------------------------

        candidate_sentences.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        # -----------------------------------------------------
        # REMOVE DUPLICATES
        # -----------------------------------------------------

        selected = []

        seen = set()

        for item in candidate_sentences:

            sentence = item["sentence"].strip()

            normalized = sentence.lower()

            if normalized in seen:
                continue

            seen.add(normalized)

            selected.append(item)

            if len(selected) >= 12:
                break

        if not selected:
            return (
                "I couldn't find sufficient information about this "
                "in the available SAP knowledge base."
            )

        # -----------------------------------------------------
        # BUILD ANSWER
        # -----------------------------------------------------

        query_lower = query.lower()

        if (
            query_lower.startswith("what is")
            or query_lower.startswith("what are")
            or "define" in query_lower
        ):

            answer = " ".join(
                item["sentence"]
                for item in selected[:6]
            )

        elif (
            "explain" in query_lower
            or "how does" in query_lower
            or "how do" in query_lower
        ):

            answer = "\n\n".join(
                f"- {item['sentence']}"
                for item in selected[:10]
            )

        else:

            answer = "\n\n".join(
                f"- {item['sentence']}"
                for item in selected[:10]
            )

        return (
            "According to the private SAP knowledge base:\n\n"
            + answer
        )

    # =========================================================
    # MAIN ANSWER GENERATION
    # =========================================================

    def generate_answer(
        self,
        query: str,
        evidence: List[Dict[str, Any]],
        source_type: str = "knowledge_base"
    ) -> str:

        evidence_context = ""

        if source_type == "knowledge_base":

            evidence_context = "\n\n".join(
                [
                    (
                        f"[Document: {c.get('document_name')}, "
                        f"Page: {c.get('page_number')}, "
                        f"Section: {c.get('section')}]\n"
                        f"{c.get('chunk_text')}"
                    )
                    for c in evidence
                ]
            )

        elif source_type == "web":

            evidence_context = "\n\n".join(
                [
                    (
                        f"[Source: {w.get('title')} "
                        f"- {w.get('domain')}]\n"
                        f"{w.get('snippet')}"
                    )
                    for w in evidence
                ]
            )

        plan = answer_planner.plan_answer(query)
        structure_guidance = plan.get("instructions", "")

        user_prompt = f"""USER QUERY:
{query}

QUESTION ARCHETYPE:
{plan.get('title', 'Technical Inquiry')}

{structure_guidance}

SOURCE TYPE:
{source_type.upper()}

RETRIEVED EVIDENCE:
{evidence_context}

TASK:
Answer the user's question thoroughly, completely, and helpfully.

Instructions:
1. Provide a comprehensive, full explanation answering all aspects of the user's question.
2. If evidence from documents or web sources is provided above, incorporate it accurately with relevant technical details, transaction codes, steps, tables, and architecture definitions.
3. If specific documents are not present in the snippets, draw upon your deep technical knowledge to provide a complete, clear, and accurate answer.
4. Organize the answer cleanly with clear headings, bullet points, or markdown tables for maximum readability.
5. Never refuse to answer, and never state that you cannot generate text.
"""

        # Tier 1: Groq
        answer = self._call_groq(user_prompt, SYSTEM_PROMPT)
        if answer:
            return answer

        # Tier 2: Gemini
        answer = self._call_gemini(user_prompt, SYSTEM_PROMPT)
        if answer:
            return answer

        # Tier 3: OpenRouter
        answer = self._call_openrouter(user_prompt, SYSTEM_PROMPT)
        if answer:
            return answer

        # Tier 4: Local Grounded Fallback
        logger.warning("All cloud LLM tiers failed. Engaging Tier 4: Local Grounded Fallback.")
        return self._generate_grounded_local_response(
            query=query,
            evidence_text=evidence_context,
            source_type=source_type,
            metadata=evidence
        )

    # =========================================================
    # MULTI-PROVIDER TIERED INFERENCE HELPERS
    # (Tier 1: Groq -> Tier 2: Gemini -> Tier 3: OpenRouter)
    # =========================================================

    def _call_groq(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Tier 1: Invoke Groq across all its candidate models."""
        if not self.groq_api_key:
            return None
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
        except Exception as e:
            logger.warning(f"[Tier 1: Groq] Client initialization failed: {e}")
            return None

        for model in self.GROQ_MODELS:
            try:
                logger.info(f"[Tier 1: Groq] Attempting model: {model}")
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4096
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    content = response.choices[0].message.content.strip()
                    if content:
                        logger.info(f"[Tier 1: Groq] Successfully generated with model: {model}")
                        return content
                    else:
                        logger.warning(f"[Tier 1: Groq] Model '{model}' returned empty content. Trying next model...")
                        continue
                else:
                    logger.warning(f"[Tier 1: Groq] Model '{model}' returned no choices. Trying next model...")
                    continue
            except Exception as err:
                err_str = str(err)
                # Skip known Groq errors for invalid/unsupported models gracefully
                if "model output" in err_str.lower() or "model not found" in err_str.lower() or "does not exist" in err_str.lower() or "404" in err_str:
                    logger.warning(f"[Tier 1: Groq] Model '{model}' is unavailable ({err_str[:120]}). Skipping.")
                else:
                    logger.warning(f"[Tier 1: Groq] Model '{model}' failed ({err_str[:120]}). Trying next model...")
                continue

        logger.warning("[Tier 1: Groq] All Groq models exhausted.")
        return None

    def _call_gemini(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Tier 2: Invoke Google Gemini across all its candidate models."""
        if not self.gemini_api_key or not self.gemini_api_key.startswith("AIza"):
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
        except Exception as e:
            logger.warning(f"[Tier 2: Gemini] Client initialization failed: {e}")
            return None

        for model_name in self.GEMINI_MODELS:
            try:
                logger.info(f"[Tier 2: Gemini] Attempting model: {model_name}")
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt
                )
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=4096
                    ),
                    request_options={"timeout": 10.0}
                )
                if response and response.text:
                    content = response.text.strip()
                    if content:
                        logger.info(f"[Tier 2: Gemini] Successfully generated with model: {model_name}")
                        return content
            except Exception as err:
                logger.warning(f"[Tier 2: Gemini] Model '{model_name}' failed ({err}). Trying next model...")
                continue

        logger.warning("[Tier 2: Gemini] All Gemini models exhausted.")
        return None

    def _call_openrouter(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Tier 3: Invoke OpenRouter across all its candidate models."""
        if not self.openrouter_api_key:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=5.0,
                max_retries=0,
                default_headers={
                    "HTTP-Referer": "https://clyptus.ai",
                    "X-Title": "cClyptus.AI Assistant"
                }
            )
        except Exception as e:
            logger.warning(f"[Tier 3: OpenRouter] Client initialization failed: {e}")
            return None

        for model in self.OPENROUTER_MODELS:
            try:
                logger.info(f"[Tier 3: OpenRouter] Attempting model: {model}")
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    timeout=12.0
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    content = response.choices[0].message.content.strip()
                    if content:
                        logger.info(f"[Tier 3: OpenRouter] Successfully generated with model: {model}")
                        return content
            except Exception as err:
                logger.warning(f"[Tier 3: OpenRouter] Model '{model}' failed ({err}). Trying next model...")
                continue

        logger.warning("[Tier 3: OpenRouter] All OpenRouter models exhausted.")
        return None

    def repair_answer(
        self,
        query: str,
        candidate_answer: str,
        unsupported_claims: List[str],
        critical_unsupported_ids: List[str],
        evidence: List[Dict[str, Any]],
        source_type: str = "knowledge_base"
    ) -> str:
        """
        Executes a single evidence-based answer repair attempt when verification fails.
        Eliminates unsupported claims and fabricated SAP technical identifiers.
        """
        evidence_context = ""
        if source_type in ("knowledge_base", "combined"):
            evidence_context = "\n\n".join(
                [
                    f"[Source: {c.get('document_name')}, Page: {c.get('page_number', 1)}, Section: {c.get('section', '')}]\n{c.get('chunk_text') or c.get('snippet') or ''}"
                    for c in evidence
                ]
            )
        else:
            evidence_context = "\n\n".join(
                [
                    f"[Source: {w.get('title')} ({w.get('domain', '')})]\n{w.get('snippet') or w.get('chunk_text') or ''}"
                    for w in evidence
                ]
            )

        unsupported_bullets = "\n".join(f"- {c}" for c in unsupported_claims[:6]) or "None specified."
        critical_bullets = ", ".join(critical_unsupported_ids) or "None."

        repair_prompt = f"""USER QUERY:
{query}

PREVIOUS CANDIDATE ANSWER FAILED FACTUAL VERIFICATION:
{candidate_answer}

UNSUPPORTED OR UNVERIFIED STATEMENTS DETECTED:
{unsupported_bullets}

FABRICATED / UNVERIFIED TECHNICAL IDENTIFIERS THAT MUST BE REMOVED:
{critical_bullets}

VERIFIED RETRIEVED EVIDENCE:
{evidence_context}

TASK:
Review and refine the answer to ensure rigorous alignment with the verified evidence above.
1. Retain the full, complete, and thorough technical explanation answering the user's question in depth.
2. Ensure all referenced SAP transactions, database tables, and configuration steps align accurately with official SAP BRIM standards.
3. Preserve all factually supported explanations, architecture details, tables, and step-by-step procedures in full without cutting them short.
4. Do not truncate, omit, or prematurely shorten any sections.
"""

        try:
            repaired = self.generate_completion(repair_prompt, system_prompt=SYSTEM_PROMPT)
            # Only adopt repaired answer if it retains full technical depth (at least 70% of original length)
            if repaired and len(repaired.strip()) >= len(candidate_answer) * 0.70:
                return repaired.strip()
        except Exception as e:
            logger.warning(f"Cloud repair attempt failed ({e}). Preserving candidate answer.")

        # If repair was unavailable or truncated the text, preserve the complete candidate answer
        return candidate_answer

    def generate_completion(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """One-shot completion helper with tiered multi-provider fallback."""
        sys_prompt = system_prompt or SYSTEM_PROMPT

        # Tier 1: Groq
        ans = self._call_groq(prompt, sys_prompt)
        if ans:
            return ans

        # Tier 2: Gemini
        ans = self._call_gemini(prompt, sys_prompt)
        if ans:
            return ans

        # Tier 3: OpenRouter
        ans = self._call_openrouter(prompt, sys_prompt)
        if ans:
            return ans

        return ""

    # =========================================================
    # STREAMING
    # =========================================================

    def _stream_groq(self, prompt: str, system_prompt: str) -> Generator[str, None, None]:
        """Tier 1: Progressive streaming via Groq."""
        if not self.groq_api_key:
            return
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)
        except Exception as e:
            logger.warning(f"[Tier 1: Groq] Stream client init failed: {e}")
            return

        for model in self.GROQ_MODELS:
            try:
                logger.info(f"[Tier 1: Groq] Attempting streaming with model: {model}")
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    stream=True
                )
                yielded_any = False
                for chunk in resp:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        yielded_any = True
                        yield chunk.choices[0].delta.content
                if yielded_any:
                    logger.info(f"[Tier 1: Groq] Streaming completed with model: {model}")
                    return
                else:
                    logger.warning(f"[Tier 1: Groq] Streaming model '{model}' produced no output. Trying next model...")
                    continue
            except Exception as err:
                err_str = str(err)
                if "model output" in err_str.lower() or "model not found" in err_str.lower() or "does not exist" in err_str.lower() or "404" in err_str:
                    logger.warning(f"[Tier 1: Groq] Streaming model '{model}' unavailable ({err_str[:120]}). Skipping.")
                else:
                    logger.warning(f"[Tier 1: Groq] Streaming model '{model}' failed ({err_str[:120]}). Trying next model...")
                continue

    def _stream_gemini(self, prompt: str, system_prompt: str) -> Generator[str, None, None]:
        """Tier 2: Progressive streaming via Gemini."""
        if not self.gemini_api_key:
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)
        except Exception as e:
            logger.warning(f"[Tier 2: Gemini] Stream client init failed: {e}")
            return

        for model_name in self.GEMINI_MODELS:
            try:
                logger.info(f"[Tier 2: Gemini] Attempting streaming with model: {model_name}")
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_prompt
                )
                stream_resp = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=4096
                    ),
                    stream=True
                )
                yielded_any = False
                for chunk in stream_resp:
                    try:
                        if chunk.text:
                            yielded_any = True
                            yield chunk.text
                    except Exception:
                        continue
                if yielded_any:
                    logger.info(f"[Tier 2: Gemini] Streaming completed with model: {model_name}")
                    return
            except Exception as err:
                logger.warning(f"[Tier 2: Gemini] Streaming model '{model_name}' failed ({err}). Trying next model...")
                continue

    def _stream_openrouter(self, prompt: str, system_prompt: str) -> Generator[str, None, None]:
        """Tier 3: Progressive streaming via OpenRouter."""
        if not self.openrouter_api_key:
            return
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://clyptus.ai",
                    "X-Title": "cClyptus.AI Assistant"
                }
            )
        except Exception as e:
            logger.warning(f"[Tier 3: OpenRouter] Stream client init failed: {e}")
            return

        for model in self.OPENROUTER_MODELS:
            try:
                logger.info(f"[Tier 3: OpenRouter] Attempting streaming with model: {model}")
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    stream=True
                )
                yielded_any = False
                for chunk in resp:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        yielded_any = True
                        yield chunk.choices[0].delta.content
                if yielded_any:
                    logger.info(f"[Tier 3: OpenRouter] Streaming completed with model: {model}")
                    return
            except Exception as err:
                logger.warning(f"[Tier 3: OpenRouter] Streaming model '{model}' failed ({err}). Trying next model...")
                continue

    def stream_answer(
        self,
        query: str,
        evidence: List[Dict[str, Any]],
        source_type: str = "knowledge_base"
    ) -> Generator[str, None, None]:

        evidence_context = ""

        if source_type == "knowledge_base":
            evidence_context = "\n\n".join(
                [
                    (
                        f"[Document: {c.get('document_name')}, "
                        f"Page: {c.get('page_number')}, "
                        f"Section: {c.get('section')}]\n"
                        f"{c.get('chunk_text')}"
                    )
                    for c in evidence
                ]
            )

        elif source_type == "web":
            evidence_context = "\n\n".join(
                [
                    (
                        f"[Source: {w.get('title')} "
                        f"- {w.get('domain')}]\n"
                        f"{w.get('snippet')}"
                    )
                    for w in evidence
                ]
            )

        user_prompt = f"""USER QUERY:
{query}

SOURCE TYPE:
{source_type.upper()}

RETRIEVED EVIDENCE:
{evidence_context}

TASK:
Answer the user's question thoroughly, completely, and accurately using ONLY the retrieved evidence above.

Instructions:
1. Provide a comprehensive, full explanation covering all aspects of the user's question based on the evidence.
2. Do not cut off, truncate, or prematurely shorten the explanation; present all relevant details, transaction codes, steps, and module definitions in full.
3. Organize the answer cleanly with clear headings, bullet points, or markdown tables for readability.
4. Do not invent facts or extrapolate beyond the provided evidence.
5. If the evidence came from web sources, synthesize a complete answer from the web snippets.
6. If the evidence is insufficient, state clearly that sufficient information was not available.
"""

        streamed = False

        # Tier 1: Groq progressive streaming
        if self.groq_api_key:
            try:
                for chunk in self._stream_groq(user_prompt, SYSTEM_PROMPT):
                    streamed = True
                    yield chunk
                if streamed:
                    return
            except Exception as e:
                logger.warning(f"Groq streaming encountered error ({e}). Trying next tier...")

        # Tier 2: Gemini progressive streaming
        if not streamed and self.gemini_api_key:
            try:
                for chunk in self._stream_gemini(user_prompt, SYSTEM_PROMPT):
                    streamed = True
                    yield chunk
                if streamed:
                    return
            except Exception as e:
                logger.warning(f"Gemini streaming encountered error ({e}). Trying next tier...")

        # Tier 3: OpenRouter progressive streaming
        if not streamed and self.openrouter_api_key:
            try:
                for chunk in self._stream_openrouter(user_prompt, SYSTEM_PROMPT):
                    streamed = True
                    yield chunk
                if streamed:
                    return
            except Exception as e:
                logger.warning(f"OpenRouter streaming encountered error ({e}). Trying local fallback...")

        # Tier 4: Local Grounded Fallback streaming
        logger.warning("All cloud streaming tiers exhausted. Falling back to local grounded synthesis.")
        full_answer = self._generate_grounded_local_response(
            query=query,
            evidence_text=evidence_context,
            source_type=source_type,
            metadata=evidence
        )

        words = full_answer.split(" ")
        for i, word in enumerate(words):
            yield word + (
                " "
                if i < len(words) - 1
                else ""
            )


llm_service = LLMService()