import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import text, func, and_
from sqlalchemy.orm import Session

from backend.app.models.message import Message
from backend.app.models.chat import Chat
from backend.app.services.embedding_service import embedding_service
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Max messages in LLM's immediate context window per turn
RECENT_CONTEXT_LIMIT = 20
SUMMARY_MAX_CHARS = 4000
SUMMARY_MESSAGE_MAX_CHARS = 500

# Sensitive patterns that must never be stored in vector embeddings or summaries
SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api_key|apikey|auth_token|access_token|private_key)\s*[:=]\s*[\"']?([^\s,\"']+)[\"']?"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9_\-\.]{15,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(postgresql|mysql|mongodb|redis)://([^:]+):([^@]+)@"), r"\1://\2:[REDACTED]@"),
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


def sanitize_for_memory(content: str) -> str:
    """Mask credentials, tokens, and private secrets before embedding or summarizing."""
    if not content:
        return ""
    sanitized = content
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class MemoryIntent:
    FIRST_MESSAGE_LOOKUP = "FIRST_MESSAGE_LOOKUP"
    LAST_MESSAGE_LOOKUP = "LAST_MESSAGE_LOOKUP"
    CROSS_CONVERSATION_RECALL = "CROSS_CONVERSATION_RECALL"
    HISTORY_RECALL = "HISTORY_RECALL"
    MIXED = "MIXED"
    CURRENT_CONTEXT = "CURRENT_CONTEXT"
    TECHNICAL_RAG = "TECHNICAL_RAG"


class ConversationMemoryService:
    """
    Production-grade Conversation Memory and Long-Term Chat Recall Service.
    
    Responsibilities:
    - Maintains strict 20-message recent context limit for LLM generation.
    - Preserves all historical messages in PostgreSQL with pgvector embeddings.
    - Provides zero-hallucination exact retrieval for first question and ordered lookups.
    - Performs semantic and lexical hybrid recall over older messages and cross-conversation chats.
    - Ensures multi-tenant user isolation (users can never access another user's memory).
    - Maintains compact rolling summaries for long conversations (> 20 messages).
    """

    @staticmethod
    def sanitize_text(value: str) -> str:
        return sanitize_for_memory(value)

    # =========================================================================
    # INTENT CLASSIFICATION
    # =========================================================================

    @classmethod
    def classify_intent(cls, query: str, chat_history: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Lightweight deterministic intent detection for conversational memory questions.
        Zero latency and zero extra LLM cost.
        """
        q = (query or "").strip().lower()
        if not q:
            return MemoryIntent.TECHNICAL_RAG

        # 1. Exact first message lookups
        first_patterns = [
            r"\b(what was|what's|show|tell me|remind me of|repeat)\s+(my\s+)?(first|initial|earliest|original)\s+(question|prompt|inquiry|query|message|topic|issue)\b",
            r"\b(what did i|what'd i)\s+(first\s+ask|ask\s+(you\s+)?(first|at the (beginning|start)|initially))\b",
            r"\bwhat did i ask (you )?at the beginning\b",
            r"\bwhat was my first question in this chat\b",
            r"\bwhat was my first question\b",
            r"\bwhat was the first question\b",
            r"\bwhat did i ask at the start\b",
            r"\bhow did (this|we|our) (chat|conversation) (start|begin)\b",
            r"\bbeginning of this chat\b",
            r"\bstart of this chat\b",
            r"\bmy earliest (question|message)\b",
        ]
        for pat in first_patterns:
            if re.search(pat, q):
                return MemoryIntent.FIRST_MESSAGE_LOOKUP

        # 2. Exact last message / previous recommendation lookups
        last_patterns = [
            r"\b(what was|what's|tell me)\s+(my\s+)?(last|previous)\s+(question|prompt|message|query)\b",
            r"\bwhat did (you|i)\s+(just\s+say|last\s+recommend|recommend\s+earlier|state\s+previously)\b",
            r"\bwhat was the last (thing|recommendation|advice|configuration) you (said|gave|suggested|shared)\b",
        ]
        for pat in last_patterns:
            if re.search(pat, q):
                return MemoryIntent.LAST_MESSAGE_LOOKUP

        # 3. Cross-conversation recall
        cross_patterns = [
            r"\b(in\s+(my\s+)?(other|another|previous|past|earlier)\s+(chat|chats|conversation|conversations|thread|session))\b",
            r"\b(discussed\s+(in\s+)?(yesterday'?s|previous|another|other)\s+(chat|conversation))\b",
            r"\bfrom (my|the) other (chat|conversation)\b",
            r"\bin (a|the) previous chat\b",
            r"\bin (a|the) different chat\b",
        ]
        for pat in cross_patterns:
            if re.search(pat, q):
                return MemoryIntent.CROSS_CONVERSATION_RECALL

        # Check for SAP technical terms to distinguish MIXED vs pure HISTORY_RECALL
        sap_technical_terms = {
            "sap", "brim", "som", "cc", "ci", "fi-ca", "fica", "convergent", "charging",
            "invoicing", "spro", "bapi", "idoc", "tcode", "t-code", "table", "billable item",
            "bit", "cit", "provider contract", "charge plan", "fpy1", "fkkbi"
        }
        has_sap_tech = any(re.search(rf"\b{re.escape(term)}\b", q) for term in sap_technical_terms)

        # 4. Long-term history recall
        history_recall_patterns = [
            r"\b(what did (we|i)\s+(discuss|talk about|mention|share|state|say))\s+\d+\s+messages?\s+ago\b",
            r"\b\d+\s+messages?\s+ago\b",
            r"\bwhich database did i mention earlier\b",
            r"\bwhat port did i (configure|mention|share|use|set)\b",
            r"\bwhat changes did we make\b",
            r"\bwhat was the issue i reported (previously|earlier)\b",
            r"\bwhat was the (error|issue|problem|bug)\s+(i|we)\s+mentioned\s+(yesterday|earlier|previously|before)\b",
            r"\bwhat did (you|i) recommend earlier\b",
            r"\bcontinue from where we (stopped|left off)\b",
            r"\bwhat was the last configuration i shared\b",
            r"\bwhat did i tell you about my previous implementation\b",
            r"\b(did i (mention|tell you|say|share)|as i (mentioned|said|told you))\b",
            r"\bwhat did (we|i)\s+(tell you|say|mention|share|discuss|talk about)\s+(earlier|previously|before|today)\b",
            r"\bwhat did we discuss\b",
            r"\bwhat were we (discussing|talking about)\b",
            r"\b(earlier|previously)\s+(in this chat|we discussed|i mentioned|i told you)\b",
            r"\b(we|i) discussed earlier\b",
            r"\bwhat (port|database|parameter|setting|config|ip|host|credentials?)\s+did i\b",
            r"\bwhat was the (configuration|setting|parameter|port|database)\s+i\b",
            r"\bthe earlier discussion\b",
            r"\bthat issue i (had|reported|mentioned)\b",
            r"\bthe earlier configuration\b",
            r"\bwhat you told me before\b",
        ]
        for pat in history_recall_patterns:
            if re.search(pat, q):
                if has_sap_tech and any(w in q for w in ["how", "connect", "integrate", "configure", "implement", "step", "guide", "procedure", "module", "relation", "use", "setup"]):
                    return MemoryIntent.MIXED
                return MemoryIntent.HISTORY_RECALL

        # 5. Immediate follow-up within current context (e.g. "explain step 2", "tell me more about this")
        current_context_patterns = [
            r"^(explain|elaborate|clarify|detail)\s+(this|that|step\s+\d+|more)\b",
            r"^(why|how)\s+so\??$",
            r"^can you give an example\??$",
            r"^what does that mean\??$",
        ]
        for pat in current_context_patterns:
            if re.search(pat, q):
                return MemoryIntent.CURRENT_CONTEXT

        # Default: If SAP keywords present -> TECHNICAL_RAG, else if ambiguous follow-up with history -> CURRENT_CONTEXT
        if has_sap_tech:
            return MemoryIntent.TECHNICAL_RAG

        if chat_history and len(chat_history) > 0 and any(p in q for p in ["it", "this", "that", "its", "why", "how", "more"]):
            return MemoryIntent.CURRENT_CONTEXT

        return MemoryIntent.TECHNICAL_RAG

    # Alias for convenience
    classify_memory_intent = classify_intent

    # =========================================================================
    # RECENT CONTEXT RETRIEVAL (STRICT 20-MESSAGE WINDOW)
    # =========================================================================

    @staticmethod
    def get_recent_messages(
        db: Session,
        chat_id: str,
        limit: int = RECENT_CONTEXT_LIMIT,
        exclude_message_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves up to `limit` (default 20) most recent messages for the current conversation.
        Results are returned in ascending chronological order (oldest to newest among the 20)
        so that prompt construction preserves natural dialogue flow.
        """
        if not chat_id:
            return []

        query = db.query(Message).filter(Message.chat_id == chat_id)
        if exclude_message_id:
            query = query.filter(Message.id != exclude_message_id)

        # Efficient indexed fetch of the last N rows
        latest_rows = (
            query
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
            .all()
        )

        # Reverse to chronological order (oldest -> newest)
        chronological = list(reversed(latest_rows))

        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "source_type": m.source_type,
                "created_at": m.created_at,
            }
            for m in chronological
        ]

    # =========================================================================
    # EXACT FIRST & LAST MESSAGE RETRIEVAL (MANDATORY EXACT RECALL)
    # =========================================================================

    @staticmethod
    def get_first_user_message(db: Session, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Direct database lookup for the earliest user question in the conversation.
        Uses stable tie-breaker (created_at ASC, id ASC) to guarantee zero fabrication.
        """
        if not chat_id:
            return None

        first_msg = (
            db.query(Message)
            .filter(Message.chat_id == chat_id, Message.role == "user")
            .order_by(Message.created_at.asc(), Message.id.asc())
            .first()
        )

        if not first_msg:
            return None

        return {
            "id": first_msg.id,
            "chat_id": first_msg.chat_id,
            "role": first_msg.role,
            "content": first_msg.content,
            "created_at": first_msg.created_at,
        }

    @staticmethod
    def get_last_user_message(
        db: Session, chat_id: str, exclude_message_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Direct database lookup for the most recent user question prior to current turn."""
        if not chat_id:
            return None

        query = db.query(Message).filter(Message.chat_id == chat_id, Message.role == "user")
        if exclude_message_id:
            query = query.filter(Message.id != exclude_message_id)

        last_msg = query.order_by(Message.created_at.desc(), Message.id.desc()).first()
        if not last_msg:
            return None

        return {
            "id": last_msg.id,
            "chat_id": last_msg.chat_id,
            "role": last_msg.role,
            "content": last_msg.content,
            "created_at": last_msg.created_at,
        }

    # =========================================================================
    # LONG-TERM MEMORY SEARCH (HYBRID VECTOR + LEXICAL)
    # =========================================================================

    def search_history(
        self,
        db: Session,
        query: str,
        user_id: str,
        current_chat_id: Optional[str] = None,
        exclude_message_ids: Optional[List[str]] = None,
        cross_conversation: bool = False,
        top_k: int = 5,
        scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search older conversation history using hybrid vector similarity and exact lexical match.
        
        Security guarantees:
        - Scoped strictly to authenticated user_id.
        - Cross-conversation search only searches other chats owned by the SAME user.
        - Never leaks another user's messages.
        """
        if scope in ("all", "cross", "cross_conversation"):
            cross_conversation = True
        cleaned_query = (query or "").strip()
        if not cleaned_query or not user_id:
            return []

        exclude_ids = set(exclude_message_ids or [])

        # Base query joining Chat for ownership validation
        base_q = db.query(Message, Chat.title).join(Chat, Chat.id == Message.chat_id).filter(Chat.user_id == user_id)

        if cross_conversation:
            # Search other chats belonging to the same user
            if current_chat_id:
                base_q = base_q.filter(Chat.id != current_chat_id)
        else:
            # Search current chat only
            if not current_chat_id:
                return []
            base_q = base_q.filter(Message.chat_id == current_chat_id)

        candidate_rows = base_q.order_by(Message.created_at.asc()).all()
        if not candidate_rows:
            return []

        # Filter out messages already in the immediate 20-message context window
        older_candidates = [
            (msg, chat_title)
            for msg, chat_title in candidate_rows
            if msg.id not in exclude_ids
        ]

        if not older_candidates:
            return []

        # Extract search query tokens (e.g. port numbers, config words, entities)
        q_tokens = [w.lower() for w in re.findall(r"\b[A-Za-z0-9_\-\.]{2,}\b", cleaned_query)]
        # Filter generic stopwords
        stopwords = {"what", "which", "where", "when", "that", "this", "about", "earlier", "previously", "message", "question", "chat"}
        significant_tokens = [t for t in q_tokens if t not in stopwords]

        query_emb = None
        try:
            query_emb = embedding_service.embed_text(cleaned_query)
        except Exception as e:
            logger.warning(f"Error computing query embedding for history search: {e}")

        scored_results: List[Tuple[float, Message, str, str]] = []

        for msg, chat_title in older_candidates:
            content_lower = msg.content.lower()
            
            # 1. Lexical score based on exact keyword / number / entity overlap
            lexical_score = 0.0
            matched_terms = []
            for token in significant_tokens:
                if token in content_lower:
                    # Give high weight to exact numerical or technical identifiers (e.g. "5434", "postgresql", "port")
                    weight = 2.0 if (token.isdigit() or len(token) >= 5) else 1.0
                    lexical_score += weight
                    matched_terms.append(token)

            norm_lexical = min(1.0, lexical_score / max(1.0, len(significant_tokens)))

            # 2. Vector cosine similarity if embeddings are available
            vector_score = 0.0
            if (
                query_emb
                and msg.embedding
                and msg.embedding_model == embedding_service.embedding_model
                and msg.embedding_version == embedding_service.embedding_version
            ):
                try:
                    # Normalized vectors -> dot product equals cosine similarity
                    v_dot = sum(a * b for a, b in zip(query_emb, msg.embedding))
                    vector_score = max(0.0, float(v_dot))
                except Exception:
                    vector_score = 0.0

            # Combined hybrid score (prefer exact term matches when specific entities are queried)
            if lexical_score > 0:
                combined_score = 0.5 * norm_lexical + 0.5 * max(vector_score, norm_lexical)
            else:
                combined_score = vector_score

            match_reason = f"Keywords matched: {', '.join(matched_terms)}" if matched_terms else "Semantic similarity"

            if combined_score > 0.15:
                scored_results.append((combined_score, msg, chat_title, match_reason))

        # Sort by highest score first, then newest
        scored_results.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)

        results = []
        for score, msg, chat_title, reason in scored_results[:top_k]:
            results.append({
                "message_id": msg.id,
                "chat_id": msg.chat_id,
                "chat_title": chat_title or "Conversation",
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
                "score": round(score, 4),
                "match_reason": reason,
            })

        return results

    # =========================================================================
    # ROLLING CONVERSATION SUMMARY MANAGEMENT
    # =========================================================================

    def get_chat_summary(self, db: Session, chat_id: str) -> Optional[str]:
        """Returns the current rolling summary of older conversation context."""
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        return chat.summary if chat else None

    def update_rolling_summary(
        self,
        db: Session,
        chat_id: str,
        new_user_msg: Optional[str] = None,
        new_assistant_msg: Optional[str] = None,
    ) -> None:
        """
        Add excerpts for messages that have left the recent context window.

        A per-chat row lock serializes writers. The timestamp/id watermark and
        summary update commit together, so a failed transaction can be retried
        without either losing progress or duplicating committed excerpts.
        The summary is intentionally lossy; full messages remain in PostgreSQL
        and can be retrieved by the separate history search.
        """
        if not chat_id:
            return
        chat = db.query(Chat).filter(Chat.id == chat_id).with_for_update().first()
        if not chat:
            return

        # Keep the newest 20 messages in the immediate context. Only summarize
        # older rows, in deterministic (created_at, id) order.
        newest = (
            db.query(Message)
            .filter(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(RECENT_CONTEXT_LIMIT + 1)
            .all()
        )
        if len(newest) <= RECENT_CONTEXT_LIMIT:
            db.commit()
            return
        cutoff = newest[RECENT_CONTEXT_LIMIT]

        pending = db.query(Message).filter(
            Message.chat_id == chat_id,
            (
                (Message.created_at < cutoff.created_at)
                | ((Message.created_at == cutoff.created_at) & (Message.id <= cutoff.id))
            ),
        )
        if chat.summary_through_created_at is not None and chat.summary_through_message_id:
            pending = pending.filter(
                (Message.created_at > chat.summary_through_created_at)
                | (
                    (Message.created_at == chat.summary_through_created_at)
                    & (Message.id > chat.summary_through_message_id)
                )
            )
        pending_rows = pending.order_by(Message.created_at.asc(), Message.id.asc()).all()
        if not pending_rows:
            db.commit()
            return

        entries = []
        for msg in pending_rows:
            safe_content = " ".join(sanitize_for_memory(msg.content or "").split())
            if len(safe_content) > SUMMARY_MESSAGE_MAX_CHARS:
                half = SUMMARY_MESSAGE_MAX_CHARS // 2
                safe_content = f"{safe_content[:half]} … {safe_content[-half:]}"
            if safe_content:
                role = "User" if msg.role == "user" else "Assistant"
                entries.append(f"{role}: {safe_content}")

        existing = (chat.summary or "").strip()
        addition = "\n".join(entries)
        combined = "\n".join(part for part in (existing, addition) if part)
        if len(combined) > SUMMARY_MAX_CHARS:
            combined = combined[-SUMMARY_MAX_CHARS:]
        chat.summary = combined or chat.summary
        last = pending_rows[-1]
        chat.summary_through_created_at = last.created_at
        chat.summary_through_message_id = last.id
        db.commit()

    # =========================================================================
    # MESSAGE EMBEDDING PERSISTENCE
    # =========================================================================

    @staticmethod
    def embed_message_content(content: str) -> Optional[List[float]]:
        """Generates a 384-dimensional vector embedding for a message after secret stripping."""
        clean = sanitize_for_memory(content).strip()
        if not clean:
            return None
        try:
            return embedding_service.embed_text(clean[:2000])
        except Exception as e:
            logger.warning(f"Could not compute message embedding: {e}")
            return None

    # =========================================================================
    # PROMPT FORMATTING HELPERS
    # =========================================================================

    @staticmethod
    def format_historical_memory_for_prompt(historical_messages: List[Dict[str, Any]]) -> str:
        """Renders retrieved historical memory passages with provenance labels for the LLM."""
        if not historical_messages:
            return ""

        blocks = []
        for i, m in enumerate(historical_messages, 1):
            role_label = "User Statement" if m["role"] == "user" else "Assistant Response"
            chat_info = f"Chat: {m.get('chat_title', 'Conversation')}"
            ts = m["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(m["created_at"], datetime) else str(m["created_at"])
            blocks.append(
                f"[M{i}] {role_label} ({chat_info} | Sent: {ts} | ID: {m.get('message_id', m.get('id', 'N/A'))}):\n{m['content']}"
            )

        return "\n\n".join(blocks)

    @staticmethod
    def format_recent_context_for_prompt(recent_messages: List[Dict[str, Any]]) -> str:
        """Renders the recent chronological dialogue context for prompt injection."""
        if not recent_messages:
            return ""

        lines = []
        for m in recent_messages:
            role_prefix = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{role_prefix}: {m['content']}")

        return "\n\n".join(lines)


conversation_memory_service = ConversationMemoryService()
