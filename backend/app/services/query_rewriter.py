import re
import logging
from typing import List, Dict, Any, Tuple
from groq import Groq
from backend.app.config import settings

logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Context-aware query resolution engine.
    Detects follow-up questions in conversations and resolves pronouns/ellipses
    into self-contained, standalone SAP queries before scope classification and retrieval.
    """

    def __init__(self):
        self.api_key = settings.LLM_API_KEY or settings.GROQ_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Groq client for query rewriter: {e}")
                self.client = None

    @staticmethod
    def is_follow_up_candidate(query: str, chat_history: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Determines whether the incoming user query is a conversational follow-up
        dependent on previous history or an independent standalone query.
        """
        if not chat_history:
            return False, "no_history"

        q = query.strip().lower()

        # 1. Sentimental questions, greetings, and chit-chat (Never rewrite as follow-up!)
        greeting_patterns = [
            r"^(hi+|hey+|hello+|howdy|hola|namaste|greetings)\b",
            r"^(good\s+(morning|afternoon|evening|night|day))\b",
            r"\b(how\s+are\s+you|how're\s+you|how\s+is\s+it\s+going|how\s+do\s+you\s+feel)\b",
            r"\b(who\s+are\s+you|what\s+is\s+your\s+name|what's\s+your\s+name)\b",
            r"\b(what\s+can\s+you\s+do|tell\s+me\s+about\s+yourself)\b",
            r"\b(thank\s+you|thanks|thx|thank\s+u)\b",
            r"\b(bye|goodbye|see\s+you|cya)\b",
            r"\b(love\s+you|hate\s+you|are\s+you\s+(happy|sad|real|human|ai|bot))\b",
            r"^(ok|okay|cool|nice|great|awesome|fine|alright|sure)\b",
        ]
        sap_mentions = [
            "sap", "brim", "convergent", "charging", "invoicing", "fi-ca", "fica",
            "som", "hana", "bapi", "idoc", "abap", "fiori", "billable item", "bit", "cit",
            "provider contract", "consumption item", "tcode", "t-code", "table"
        ]
        has_sap = any(t in q for t in sap_mentions)

        for pat in greeting_patterns:
            if re.search(pat, q, re.IGNORECASE) and not has_sap:
                return False, "sentimental_or_greeting"

        # 2. Unrelated non-SAP queries (Never rewrite or force SAP into these!)
        unrelated_patterns = [
            r"\b(weather|temperature|rain|forecast)\b",
            r"\b(joke|funny|riddle)\b",
            r"\b(cricket|football|soccer|basketball|sports|ipl|olympics)\b",
            r"\b(recipe|cook|bake|dinner|lunch|breakfast|food)\b",
            r"\b(movie|cinema|actor|actress|song|singer|music)\b",
            r"\b(python|javascript|typescript|c\+\+|java|golang|rust|php|ruby)\b",
            r"\b(elon musk|donald trump|biden|modi)\b"
        ]
        for pat in unrelated_patterns:
            if re.search(pat, q, re.IGNORECASE) and not has_sap:
                return False, "unrelated_standalone"

        # 3. Short contextual query triggers
        short_followup_triggers = [
            r"^can you explain in detail",
            r"^explain in detail",
            r"^explain more",
            r"^tell me more",
            r"^more details",
            r"^why\??$",
            r"^how\??$",
            r"^how so\??$",
            r"^give (an|a) example",
            r"^provide (an|a) example",
            r"^explain this",
            r"^explain that",
            r"^what does this mean",
            r"^what about",
            r"^how is it configured",
            r"^what are the steps",
            r"^what are the prerequisites",
            r"^why is this important",
            r"^what are (the )?(important )?transactions",
            r"^what are (the )?benefits",
            r"^what are (the )?limitations",
            r"^what are its benefits",
            r"^what are its components"
        ]
        for trigger in short_followup_triggers:
            if re.search(trigger, q, re.IGNORECASE):
                return True, "short_contextual_query"

        # 4. Pronoun / anaphoric reference triggers
        pronoun_patterns = [
            r"\b(does|can|is|will|how|what|why|where)\s+it\b",
            r"\b(what|how|why)\s+(does|is)\s+this\b",
            r"\bwhat happens after that\b",
            r"\bwhat happens next\b",
            r"\bwhat happens after\b",
            r"\b(contain|include|consist of)\s+it\b",
            r"\bdoes it contain\b",
            r"\bwhat information does it\b",
            r"\bhow does it integrate\b",
            r"\bhow is it\b",
            r"\bwhy is it\b",
            r"\bwhat are its\b",
            r"\bits\s+(components|benefits|tables|tcodes|steps|features)\b"
        ]
        for pat in pronoun_patterns:
            if re.search(pat, q, re.IGNORECASE):
                return True, "pronoun_reference"

        # 5. Short queries (< 6 words) with explicit continuation or anaphoric intent
        continuation_keywords = {
            "it", "this", "that", "its", "why", "how", "more", "next", "after",
            "steps", "step", "example", "prerequisites", "prerequisite", "transactions",
            "transaction", "tcodes", "tcode", "tables", "table", "process", "detail",
            "details", "configuration", "configured", "integrate", "integration", "benefits",
            "limitations", "difference", "compare"
        }
        word_tokens = set(re.findall(r"\b\w+\b", q))
        if len(q.split()) <= 5 and not has_sap and (word_tokens & continuation_keywords):
            return True, "short_elliptical_query"

        # 6. Queries with ambiguous references like "after rating", "integrate with CI"
        if ("after rating" in q or "with ci" in q or "with cc" in q) and not ("sap convergent" in q):
            return True, "ambiguous_abbreviation_or_phase"

        # 7. Standalone SAP query (do not over-rewrite)
        if has_sap and not any(p in word_tokens for p in ["it", "this", "that", "its"]):
            return False, "standalone_sap"

        return False, "default_standalone"

    @staticmethod
    def extract_recent_topic(chat_history: List[Dict[str, Any]]) -> str:
        """
        Extracts the most recent relevant SAP entity/topic from conversation history.
        Inspects recent user turns in reverse chronological order.
        """
        for msg in reversed(chat_history):
            content = msg.get("content", "").strip()
            if not content:
                continue

            # Skip rejected/refusal messages
            if msg.get("source_type") == "refusal":
                continue

            if msg.get("role") == "user":
                # Clean prompt prefixes
                clean = re.sub(
                    r"^(what is a|what is an|what is the|what is|what are|explain the|explain|tell me about|how does|can you)\s+",
                    "",
                    content,
                    flags=re.IGNORECASE
                )
                clean = clean.rstrip("?.,!").strip()
                # Ignore generic meta queries and greetings
                if len(clean) > 3 and not any(clean.lower().startswith(w) for w in ["explain in detail", "tell me more", "how it", "hi", "hello", "why"]):
                    return clean

            if msg.get("role") == "assistant":
                # Check markdown headings in assistant messages
                heading_match = re.search(r"##\s*([^\n]+)", content)
                if heading_match:
                    h = heading_match.group(1).replace("Overview", "").strip(" -–:")
                    if len(h) > 3 and not any(w in h.lower() for w in ["integration", "summary", "guardrail"]):
                        return h

        return "SAP BRIM"

    def rewrite_heuristic(self, query: str, topic: str) -> str:
        """
        Deterministic, zero-latency fallback rewriter when LLM is unavailable.
        """
        q = query.strip()
        q_lower = q.lower()

        # Expand common SAP BRIM abbreviations
        ci_expanded = re.sub(r"\bCI\b", "SAP Convergent Invoicing", q, flags=re.IGNORECASE)
        cc_expanded = re.sub(r"\bCC\b", "SAP Convergent Charging", ci_expanded, flags=re.IGNORECASE)

        # "can you explain in detail" / "explain in detail"
        if re.search(r"^(can you )?explain in detail", q_lower):
            return f"Explain {topic} in detail."

        # "what information does it contain"
        if "what information does it contain" in q_lower or "what does it contain" in q_lower:
            return f"What information does {topic} contain?"

        # "how does it integrate with ..."
        integrate_match = re.search(r"how does it integrate with (.+)", cc_expanded, re.IGNORECASE)
        if integrate_match:
            target = integrate_match.group(1).rstrip("?.,!")
            return f"How does {topic} integrate with {target}?"

        # "what happens after that" / "what happens next"
        if "what happens after that" in q_lower or "what happens next" in q_lower:
            return f"What happens after the relevant stage in {topic}?"

        # "what happens after rating"
        if "what happens after rating" in q_lower:
            return f"What happens after rating in {topic}?"

        # "what are the important transactions"
        if "important transactions" in q_lower:
            return f"What are the important transactions related to {topic}?"

        # Generic pronoun replacement
        replaced = re.sub(r"\bit\b", topic, cc_expanded, flags=re.IGNORECASE)
        replaced = re.sub(r"\bthis\b", topic, replaced, flags=re.IGNORECASE)
        replaced = re.sub(r"\bits\b", f"{topic}'s", replaced, flags=re.IGNORECASE)

        if replaced != q:
            return replaced

        return f"{q} regarding {topic}"

    def resolve_query(self, query: str, chat_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes complete conversational resolution pipeline:
        1. Context detection & follow-up classification
        2. Extraction of previous conversation topic
        3. High-precision LLM rewrite with Groq (or deterministic heuristic fallback)
        """
        cleaned_query = query.strip()
        if not chat_history:
            return {
                "original_query": cleaned_query,
                "is_follow_up": False,
                "conversation_topic": None,
                "resolved_query": cleaned_query,
                "reason": "no_history"
            }

        is_follow_up, reason = self.is_follow_up_candidate(cleaned_query, chat_history)
        if not is_follow_up:
            return {
                "original_query": cleaned_query,
                "is_follow_up": False,
                "conversation_topic": None,
                "resolved_query": cleaned_query,
                "reason": reason
            }

        topic = self.extract_recent_topic(chat_history)

        # Attempt high-precision LLM rewrite via Groq
        if self.client:
            try:
                system_prompt = (
                    "You are a query rewriting engine for an SAP enterprise assistant.\n"
                    "Given recent conversation history and the latest user query:\n"
                    "1. If the latest query is a follow-up or contains pronouns ('it', 'this', 'that', 'its') "
                    "or contextual requests ('explain in detail', 'what happens next', 'how does it integrate', 'transactions'), "
                    "rewrite it into a self-contained, standalone question incorporating the most recent relevant SAP topic from history. "
                    "Expand abbreviations in context (e.g. CI -> SAP Convergent Invoicing, CC -> SAP Convergent Charging, FI-CA -> SAP FI-CA).\n"
                    "2. If the query is already standalone, or is completely unrelated to the SAP conversation "
                    "(e.g. asking about weather, sports, jokes, non-SAP topics), output the query EXACTLY as submitted. Do not force SAP into unrelated queries.\n"
                    "3. Output ONLY the standalone question without explanation or quotation marks."
                )

                hist_text = "\n".join([
                    f"{m.get('role', 'user').capitalize()}: {m.get('content', '')[:300]}"
                    for m in chat_history[-4:]
                ])
                user_msg = f"Conversation History:\n{hist_text}\n\nLatest User Query: {cleaned_query}\n\nStandalone Question:"

                candidate_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
                for model in candidate_models:
                    try:
                        res = self.client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_msg}
                            ],
                            temperature=0.0,
                            max_tokens=100
                        )
                        rewritten = res.choices[0].message.content.strip().strip('"\'')
                        if rewritten and len(rewritten) > 3:
                            return {
                                "original_query": cleaned_query,
                                "is_follow_up": True,
                                "conversation_topic": topic,
                                "resolved_query": rewritten,
                                "reason": f"llm_rewriter_{model}"
                            }
                    except Exception as llm_err:
                        logger.warning(f"Model '{model}' query rewriting error: {llm_err}")
                        continue
            except Exception as e:
                logger.warning(f"LLM query rewriter error: {e}")

        # Fallback to heuristic rewriter
        heuristic_resolved = self.rewrite_heuristic(cleaned_query, topic)
        return {
            "original_query": cleaned_query,
            "is_follow_up": True,
            "conversation_topic": topic,
            "resolved_query": heuristic_resolved,
            "reason": "heuristic_fallback"
        }


query_rewriter = QueryRewriter()
