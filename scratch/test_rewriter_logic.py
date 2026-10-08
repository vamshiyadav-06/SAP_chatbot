import re
import os
from typing import List, Dict, Any, Tuple
from groq import Groq
from backend.app.config import settings

class QueryRewriter:
    def __init__(self):
        self.api_key = settings.LLM_API_KEY or settings.GROQ_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception:
                self.client = None

    @staticmethod
    def is_follow_up_candidate(query: str, chat_history: List[Dict[str, Any]]) -> Tuple[bool, str]:
        if not chat_history:
            return False, "no_history"

        q = query.strip().lower()

        # 1. Check for blatantly unrelated non-SAP queries
        unrelated_patterns = [
            r"\b(weather|temperature|rain|forecast)\b",
            r"\b(joke|funny|riddle)\b",
            r"\b(cricket|football|soccer|basketball|sports|ipl|olympics)\b",
            r"\b(recipe|cook|bake|dinner|lunch|breakfast|food)\b",
            r"\b(movie|cinema|actor|actress|song|singer|music)\b",
            r"\b(python|javascript|typescript|c\+\+|java|golang|rust)\b",
            r"\b(elon musk|donald trump|biden|modi)\b"
        ]
        # Only treat as unrelated if query does NOT also mention SAP terms
        sap_mentions = ["sap", "brim", "convergent", "fi-ca", "fica", "hana", "bapi", "idoc"]
        has_sap = any(t in q for t in sap_mentions)
        for pat in unrelated_patterns:
            if re.search(pat, q, re.IGNORECASE) and not has_sap:
                return False, "unrelated_standalone"

        # 2. Check for follow-up triggers
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

        # 3. Check for pronoun / reference based queries
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
            r"\bits\s+(components|benefits|tables|tcodes|steps)\b"
        ]
        for pat in pronoun_patterns:
            if re.search(pat, q, re.IGNORECASE):
                return True, "pronoun_reference"

        # 4. Check if query is short (< 6 words) and lacks explicit noun subject
        words = q.split()
        if len(words) <= 5 and not has_sap:
            return True, "short_elliptical_query"

        # 5. Check if query is already standalone SAP
        if has_sap and not any(p in words for p in ["it", "this", "that", "its"]):
            return False, "standalone_sap"

        return False, "default_standalone"

    @staticmethod
    def extract_recent_topic(chat_history: List[Dict[str, Any]]) -> str:
        # Search backward through user queries first, then assistant
        for msg in reversed(chat_history):
            content = msg.get("content", "").strip()
            if not content:
                continue
            
            # Check user queries
            if msg.get("role") == "user":
                # Match patterns like: "What is [X]?", "Explain [X]", "What is a [X] in [Y]?"
                clean_c = re.sub(r"^(what is a|what is an|what is the|what is|what are|explain the|explain|tell me about)\s+", "", content, flags=re.IGNORECASE)
                clean_c = clean_c.rstrip("?.,!").strip()
                if len(clean_c) > 3 and not any(clean_c.lower().startswith(w) for w in ["can you", "how does", "tell me"]):
                    return clean_c

            # Check assistant titles/headings if user query was too short
            if msg.get("role") == "assistant":
                heading_match = re.search(r"##\s*([^\n]+)", content)
                if heading_match:
                    h = heading_match.group(1).replace("Overview", "").strip(" -–:")
                    if len(h) > 3:
                        return h

        return "SAP"

    def rewrite_heuristic(self, query: str, topic: str) -> str:
        q = query.strip()
        q_lower = q.lower()

        # CI abbreviation expansion
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

        # Attempt LLM rewrite using Groq
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
                hist_text = "\n".join([f"{m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in chat_history[-4:]])
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
                    except Exception:
                        continue
            except Exception:
                pass

        # Fallback to heuristic rewriter
        heuristic_resolved = self.rewrite_heuristic(cleaned_query, topic)
        return {
            "original_query": cleaned_query,
            "is_follow_up": True,
            "conversation_topic": topic,
            "resolved_query": heuristic_resolved,
            "reason": "heuristic_fallback"
        }

if __name__ == '__main__':
    rewriter = QueryRewriter()
    test_cases = [
        {
            'name': 'Test 1: Explain in detail',
            'history': [{'role': 'user', 'content': 'What is SAP Convergent Invoicing?'}, {'role': 'assistant', 'content': 'SAP Convergent Invoicing is...'}],
            'query': 'can you explain in detail'
        },
        {
            'name': 'Test 2: Billable item pronoun',
            'history': [{'role': 'user', 'content': 'What is a Billable Item in SAP Convergent Invoicing?'}, {'role': 'assistant', 'content': 'A Billable Item is...'}],
            'query': 'what information does it contain?'
        },
        {
            'name': 'Test 3: CC integration with CI',
            'history': [{'role': 'user', 'content': 'Explain SAP Convergent Charging.'}, {'role': 'assistant', 'content': 'SAP Convergent Charging performs rating...'}],
            'query': 'How does it integrate with CI?'
        },
        {
            'name': 'Test 4: Weather query',
            'history': [{'role': 'user', 'content': 'Explain SAP BRIM.'}, {'role': 'assistant', 'content': 'SAP BRIM is...'}],
            'query': 'What is the weather today?'
        },
        {
            'name': 'Test 5: Python joke',
            'history': [{'role': 'user', 'content': 'Explain SAP Convergent Invoicing.'}, {'role': 'assistant', 'content': 'SAP CI is...'}],
            'query': 'Tell me a Python joke.'
        },
        {
            'name': 'Test 6: Multi-turn after rating',
            'history': [
                {'role': 'user', 'content': 'What is SAP BRIM?'}, {'role': 'assistant', 'content': 'SAP BRIM is...'},
                {'role': 'user', 'content': 'Explain Convergent Charging.'}, {'role': 'assistant', 'content': 'Convergent Charging is the rating engine...'}
            ],
            'query': 'What happens after rating?'
        },
        {
            'name': 'Test 7: Important transactions',
            'history': [{'role': 'user', 'content': 'Explain FI-CA in SAP BRIM.'}, {'role': 'assistant', 'content': 'FI-CA is...'}],
            'query': 'What are the important transactions?'
        }
    ]

    for tc in test_cases:
        res = rewriter.resolve_query(tc['query'], tc['history'])
        print(f"=== {tc['name']} ===")
        print(f"Original: {res['original_query']}")
        print(f"Follow-up: {res['is_follow_up']}")
        print(f"Topic: {res['conversation_topic']}")
        print(f"Resolved: {res['resolved_query']}")
        print(f"Reason: {res['reason']}\n")
