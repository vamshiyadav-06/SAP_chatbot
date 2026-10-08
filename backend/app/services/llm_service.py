import os
import re
import logging
from typing import List, Dict, Any, Generator

from backend.app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an SAP Knowledge Assistant.

Your scope is strictly SAP and SAP-related topics.

Answer ONLY from the evidence supplied by the retrieval system.

Never invent facts.
Never use general pretrained knowledge as evidence.
Never claim that information exists in the private knowledge base unless the supplied evidence supports it.

For answers:
- Provide a full, complete, and comprehensive explanation answering all aspects of the user's question.
- Do not prematurely truncate, summarize excessively, or cut your answer short.
- Preserve all important SAP technical terms, transaction codes, tables, module names, and architecture definitions.
- Organize your response logically with clear sections, bullet points, or tables where appropriate.
- Do not reproduce document headers, confidentiality notices, or unnecessary metadata.
- Do not mention information that is not supported by the retrieved evidence.

For web answers:
- Use the supplied web evidence thoroughly.
- Explain the key concepts and steps fully.

If the evidence is insufficient, explicitly say that the information could not be verified.

For non-SAP questions, refuse briefly.

Be precise, comprehensive, factual, and strictly evidence-grounded."""


class LLMService:

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()

        self.api_key = (
            settings.LLM_API_KEY
            or settings.GROQ_API_KEY
            or os.getenv("OPENAI_API_KEY", "")
        )

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
            return (
                "I couldn't find sufficient information about this "
                "in the available SAP knowledge base."
            )

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

        # =====================================================
        # CLOUD LLM
        # =====================================================

        if self.api_key:

            try:

                is_xai = self.api_key.startswith("xai-") or "grok" in self.provider
                is_groq = "groq" in self.provider or self.api_key.startswith("gsk_")

                if is_xai:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=self.api_key,
                        base_url="https://api.x.ai/v1"
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "grok-2",
                        "grok-2-latest",
                        "grok-beta",
                        "grok-vision-beta"
                    ]
                elif is_groq:
                    from groq import Groq
                    client = Groq(
                        api_key=self.api_key
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "openai/gpt-oss-120b",
                        "openai/gpt-oss-20b",
                        "qwen/qwen3.8-27b",
                        "llama-3.3-70b-versatile",
                        "llama-3.1-70b-versatile",
                        "llama-3.1-8b-instant",
                        "mixtral-8x7b-32768",
                        "gemma2-9b-it"
                    ]
                else:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=self.api_key
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "gpt-4o-mini",
                        "gpt-4o",
                        "gpt-3.5-turbo"
                    ]

                # De-duplicate candidate models while preserving priority order
                unique_models = []
                for m in candidate_models:
                    if m and m not in unique_models:
                        unique_models.append(m)

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

                # Automatically try each model in order; if one fails, choose the next model
                last_error = None
                for current_model in unique_models:
                    try:
                        logger.info(f"Attempting LLM inference with model: {current_model}")
                        response = client.chat.completions.create(
                            model=current_model,
                            messages=[
                                {
                                    "role": "system",
                                    "content": SYSTEM_PROMPT
                                },
                                {
                                    "role": "user",
                                    "content": user_prompt
                                }
                            ],
                            temperature=0.1,
                            max_tokens=4096
                        )
                        return response.choices[0].message.content.strip()
                    except Exception as model_err:
                        logger.warning(f"Model '{current_model}' encountered error ({model_err}). Automatically trying next model...")
                        last_error = model_err
                        continue

                if last_error:
                    raise last_error

            except Exception as e:
                logger.warning(
                    f"Cloud LLM error ({e}). "
                    "Using local grounded synthesis."
                )

        # =====================================================
        # LOCAL FALLBACK
        # =====================================================

        return self._generate_grounded_local_response(
            query=query,
            evidence_text=evidence_context,
            source_type=source_type,
            metadata=evidence
        )

    # =========================================================
    # STREAMING
    # =========================================================

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

        # =====================================================
        # CLOUD LLM STREAMING
        # =====================================================

        if self.api_key:
            try:
                is_xai = self.api_key.startswith("xai-") or "grok" in self.provider
                is_groq = "groq" in self.provider or self.api_key.startswith("gsk_")

                if is_xai:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=self.api_key,
                        base_url="https://api.x.ai/v1"
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "grok-2",
                        "grok-2-latest",
                        "grok-beta"
                    ]
                elif is_groq:
                    from groq import Groq
                    client = Groq(
                        api_key=self.api_key
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "openai/gpt-oss-120b",
                        "openai/gpt-oss-20b",
                        "qwen/qwen3.8-27b",
                        "llama-3.3-70b-versatile",
                        "llama-3.1-70b-versatile"
                    ]
                else:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=self.api_key
                    )
                    candidate_models = [
                        settings.LLM_MODEL,
                        "gpt-4o-mini",
                        "gpt-4o",
                        "gpt-3.5-turbo"
                    ]

                unique_models = []
                for m in candidate_models:
                    if m and m not in unique_models:
                        unique_models.append(m)

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

                last_error = None
                for current_model in unique_models:
                    try:
                        logger.info(f"Attempting progressive streaming inference with model: {current_model}")
                        stream_resp = client.chat.completions.create(
                            model=current_model,
                            messages=[
                                {
                                    "role": "system",
                                    "content": SYSTEM_PROMPT
                                },
                                {
                                    "role": "user",
                                    "content": user_prompt
                                }
                            ],
                            temperature=0.1,
                            max_tokens=4096,
                            stream=True
                        )

                        streamed_any = False
                        for chunk in stream_resp:
                            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                                streamed_any = True
                                yield chunk.choices[0].delta.content

                        if streamed_any:
                            return
                    except Exception as model_err:
                        logger.warning(f"Model '{current_model}' streaming error ({model_err}). Trying next candidate...")
                        last_error = model_err
                        continue

                if last_error:
                    logger.warning(f"All cloud LLM streaming models failed ({last_error}). Falling back to local grounded response.")

            except Exception as e:
                logger.warning(
                    f"Cloud LLM streaming setup error ({e}). "
                    "Using local grounded synthesis."
                )

        # =====================================================
        # LOCAL FALLBACK STREAMING
        # =====================================================

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