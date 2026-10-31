import re
import logging
from typing import List, Dict, Any, Set, Tuple, Optional
from backend.app.config import settings
from backend.app.retrieval.source_registry import hostname_matches
from backend.app.schemas.grounded_generation import PackedChunk, ContextPackingResult

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "what", "is", "the", "a", "an", "how", "to", "in", "of", "and", "for", "with",
    "does", "do", "explain", "describe", "can", "you", "tell", "me", "about", "which",
    "are", "why", "where", "when", "by", "from", "on", "at", "as", "into"
}

# Module detection regex and keywords
MODULE_PATTERNS = {
    "SOM": [r"\bsom\b", r"subscription\s+order\s+management", r"provider\s+order", r"solution\s+quotation", r"provider\s+contract"],
    "CC": [r"\bcc\b", r"convergent\s+charging", r"charge\s+plan", r"range\s+table", r"rating\s+logic", r"pricing\s+tree", r"core\s+tool"],
    "CI": [r"\bci[0-9]?\b", r"convergent\s+invoicing", r"billable\s+item", r"consumption\s+item", r"\bbit\b", r"\bcit\b", r"billing\s+order"],
    "FI-CA": [r"fi[- ]?ca\b", r"\bfica\b", r"contract\s+accounts?\s+receivable", r"contract\s+account", r"open\s+items?", r"dfkkop", r"payment\s+lot"],
    "RAR": [r"\brar\b", r"revenue\s+accounting", r"\brai\b", r"\bpob\b", r"\bssp\b", r"ifrs\s*15", r"standalone\s+selling\s+price", r"performance\s+obligation"],
    "RAP": [r"\brap\b", r"abap\s+restful", r"behavior\s+definition", r"cds\s+view"],
    "Security": [r"authorization", r"pfcg", r"fiori\s+catalog", r"security\s+role"]
}

# Document tier definitions and mapping
try:
    from backend.app.corpus.tier_definitions import DOCUMENT_TIER_MAPPING
except ImportError:
    DOCUMENT_TIER_MAPPING = {}

TIER_RANK_PREFERENCE = {
    "official_sap": 0,
    "sap_partner_or_book": 1,
    "book": 1,
    "official-sap-domain": 2,
    "official_sap_domain": 2,
    "self_authored": 3,
    "forum": 4
}


class ContextPackingService:
    """
    Step 2 Context Packing Service with User Corrections:
    - Ranks by relevance * configurable tier weight (not tier first)
    - Deduplicates near-identical chunks keeping highest-tier copy
    - Scales token budget dynamically with detected question modules (base + per-module)
    - Splits web tier into official-sap-domain vs forum
    - Implements optional sentence-level compression behind config flag
    - Identifies uncovered modules for partial answer generation
    """

    def __init__(self):
        self.calibrated_threshold = getattr(settings, "RETRIEVAL_CALIBRATED_THRESHOLD", 0.45)
        self.base_budget = getattr(settings, "CONTEXT_BASE_TOKEN_BUDGET", 1500)
        self.per_module_budget = getattr(settings, "CONTEXT_PER_MODULE_TOKEN_BUDGET", 600)
        self.max_token_limit = getattr(settings, "CONTEXT_PACKING_TOKEN_LIMIT", 3500)
        self.dedupe_threshold = getattr(settings, "DEDUPE_SIMILARITY_THRESHOLD", 0.85)

    @staticmethod
    def detect_modules(text: str) -> List[str]:
        """Detects SAP modules mentioned in query or chunk text."""
        detected = []
        text_lower = text.lower()
        for mod, patterns in MODULE_PATTERNS.items():
            for p in patterns:
                if re.search(p, text_lower):
                    detected.append(mod)
                    break
        return detected

    def infer_chunk_tier(self, chunk: Dict[str, Any]) -> str:
        """
        Determines the authority tier of a chunk:
        - official_sap
        - sap_partner_or_book (alias: book)
        - official-sap-domain (help.sap.com, learning.sap.com, support.sap.com)
        - forum (community.sap.com, blogs.sap.com)
        - self_authored
        """
        url = (chunk.get("url") or "").lower()
        source_type = chunk.get("source_type") or ""

        # Web tier classification
        if source_type == "web" or url.startswith("http"):
            sap_documentation = hostname_matches(url, "sap.com") and "/documentation" in url
            if any(hostname_matches(url, dom) for dom in ["help.sap.com", "learning.sap.com", "support.sap.com"]) or sap_documentation:
                return "official-sap-domain"
            return "forum"

        doc_name = (chunk.get("document_name") or chunk.get("source") or "").strip()
        tier_field = chunk.get("source_tier") or chunk.get("provenance_tier") or chunk.get("tier") or chunk.get("authority_tier_name")
        if tier_field in TIER_RANK_PREFERENCE:
            return tier_field

        # Canonical lookup from DOCUMENT_TIER_MAPPING if available
        if doc_name in DOCUMENT_TIER_MAPPING:
            canonical_tier = DOCUMENT_TIER_MAPPING[doc_name]["tier"]
            # Map canonical "sap_partner_or_book" to "book" alias for backward compatibility if needed
            return canonical_tier

        # Case-insensitive filename matching for canonical mapping
        for known_doc, meta in DOCUMENT_TIER_MAPPING.items():
            if known_doc.lower() == doc_name.lower():
                return meta["tier"]

        # AI-written, summary, cookbook, or Q-bank files MUST be self_authored
        if any(term in doc_name.lower() for term in [
            "100 ans", "ai architect", "q bank", "cookbook", "handbook", "guide",
            "synthetic", "self", "custom", "test_doc", "reversal process"
        ]):
            return "self_authored"

        # Published books
        if any(b in doc_name.lower() for b in ["press book", "e_book", "catalog"]):
            return "sap_partner_or_book"

        # Official SAP courseware and product manuals
        if any(sap_term in doc_name.lower() for sap_term in [
            "ac240", "br234", "pdfdownload", "device_as_a_service",
            "sap cc.pdf", "sap ci", "mg.pdf", "simpl_op"
        ]):
            return "official_sap"

        return "self_authored"

    def get_tier_weight(self, tier: str) -> float:
        """Retrieves configurable tier multiplier weight."""
        if tier == "official_sap":
            return getattr(settings, "TIER_WEIGHT_OFFICIAL_SAP", 1.0)
        elif tier in ("sap_partner_or_book", "book"):
            return getattr(settings, "TIER_WEIGHT_BOOK", 0.85)
        elif tier in ("official-sap-domain", "official_sap_domain"):
            return getattr(settings, "TIER_WEIGHT_OFFICIAL_WEB", 0.80)
        elif tier == "forum":
            return getattr(settings, "TIER_WEIGHT_FORUM_WEB", 0.50)
        elif tier == "self_authored":
            return getattr(settings, "TIER_WEIGHT_SELF_AUTHORED", 0.60)
        return getattr(settings, "TIER_WEIGHT_SELF_AUTHORED", 0.60)

    def infer_chunk_module(self, chunk: Dict[str, Any]) -> str:
        """Determines primary SAP module for a chunk."""
        if chunk.get("module") and chunk["module"] in MODULE_PATTERNS:
            return chunk["module"]

        doc_name = (chunk.get("document_name") or chunk.get("source") or "").strip()
        text = chunk.get("chunk_text") or chunk.get("text") or ""

        doc_mods = self.detect_modules(doc_name)
        if doc_mods:
            return doc_mods[0]

        content_mods = self.detect_modules(text)
        if content_mods:
            return content_mods[0]

        return "General"

    @staticmethod
    def _token_set(text: str) -> Set[str]:
        words = re.findall(r"\b[a-zA-Z0-9_\-]+\b", text.lower())
        return {w for w in words if w not in STOP_WORDS and len(w) > 2}

    def _is_near_duplicate(self, text_a: str, text_b: str) -> bool:
        """Calculates Jaccard token overlap between two texts."""
        set_a = self._token_set(text_a)
        set_b = self._token_set(text_b)
        if not set_a or not set_b:
            return False
        inter = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return (inter / float(union)) >= self.dedupe_threshold if union > 0 else False

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        words = text.split()
        return max(1, int(len(words) * 1.33))

    def _compress_sentences(self, text: str) -> str:
        """Optional sentence-level compression pruning low-value boilerplate."""
        if not getattr(settings, "ENABLE_SENTENCE_COMPRESSION", False):
            return text

        boilerplate_patterns = [
            r"all rights reserved",
            r"confidential and proprietary",
            r"for more information visit",
            r"page\s+\d+\s+of\s+\d+",
            r"printed in germany",
            r"sap se or an sap affiliate"
        ]
        sentences = re.split(r"(?<=[.!?])\s+", text)
        filtered = []
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            s_lower = s_clean.lower()
            if any(re.search(bp, s_lower) for bp in boilerplate_patterns):
                continue
            filtered.append(s_clean)
        return " ".join(filtered) if filtered else text

    def compute_dynamic_budget(self, detected_modules: List[str]) -> int:
        """Scales token budget dynamically: base + per-module budget."""
        budget = self.base_budget + len(detected_modules) * self.per_module_budget
        return min(budget, self.max_token_limit)

    def pack_context(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        token_limit: Optional[int] = None
    ) -> ContextPackingResult:
        """
        Packs retrieved chunks with all requested corrections:
        1. Ranks by relevance x configurable tier weight (not tier first).
        2. Deduplication keeps the highest-tier copy.
        3. Scales budget dynamically with detected modules.
        4. Identifies covered vs uncovered modules for partial answers with gaps.
        """
        detected_modules = self.detect_modules(query)
        dynamic_budget = token_limit or self.compute_dynamic_budget(detected_modules)

        if not retrieved_chunks:
            return ContextPackingResult(
                packed_chunks=[],
                packed_text="",
                detected_question_modules=detected_modules,
                covered_question_modules=[],
                uncovered_question_modules=detected_modules,
                is_insufficient=True,
                top_score=0.0,
                closest_sources=[],
                total_estimated_tokens=0,
                token_budget=dynamic_budget
            )

        # 1. Top relevance score check
        top_score = max(
            [float(c.get("score") or c.get("rerank_score") or c.get("similarity") or 0.0) for c in retrieved_chunks],
            default=0.0
        )

        closest_sources = [
            {
                "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                "document_name": c.get("document_name") or c.get("source") or "Document",
                "page_number": int(c.get("page_number") or c.get("page") or 1),
                "score": float(c.get("score") or c.get("rerank_score") or c.get("similarity") or 0.0),
                "tier": self.infer_chunk_tier(c),
                "module": self.infer_chunk_module(c)
            }
            for c in retrieved_chunks[:5]
        ]

        if top_score < self.calibrated_threshold:
            logger.info(f"Top score {top_score:.3f} below threshold {self.calibrated_threshold:.3f}.")
            return ContextPackingResult(
                packed_chunks=[],
                packed_text="",
                detected_question_modules=detected_modules,
                covered_question_modules=[],
                uncovered_question_modules=detected_modules,
                is_insufficient=True,
                top_score=top_score,
                closest_sources=closest_sources,
                total_estimated_tokens=0,
                token_budget=dynamic_budget
            )

        # 2. Enrich candidate chunks with tier weights and final rank score
        candidates: List[PackedChunk] = []
        for c in retrieved_chunks:
            cid = str(c.get("chunk_id") or c.get("id") or "")
            tier = self.infer_chunk_tier(c)
            mod = self.infer_chunk_module(c)
            src = (c.get("document_name") or c.get("source") or "Document").strip()
            page = int(c.get("page_number") or c.get("page") or 1)
            raw_text = (c.get("chunk_text") or c.get("text") or "").strip()
            compressed_text = self._compress_sentences(raw_text)
            relevance_score = float(c.get("score") or c.get("rerank_score") or c.get("similarity") or 0.0)
            weight = self.get_tier_weight(tier)
            final_score = relevance_score * weight

            candidates.append(
                PackedChunk(
                    chunk_id=cid,
                    tier=tier,
                    module=mod,
                    source=src,
                    page=page,
                    text=compressed_text,
                    score=relevance_score,
                    tier_weight=weight,
                    final_rank_score=final_score
                )
            )

        # 3. Deduplication: when near-duplicates occur, KEEP HIGHEST-TIER COPY
        # Sort candidates primarily by tier preference ascending (highest authority first), then score descending
        tier_sorted = sorted(
            candidates,
            key=lambda x: (TIER_RANK_PREFERENCE.get(x.tier, 99), -x.score)
        )
        deduped: List[PackedChunk] = []
        for cand in tier_sorted:
            # Check if near-duplicate exists in already accepted deduped list
            dup_found = False
            for existing in deduped:
                if self._is_near_duplicate(cand.text, existing.text):
                    dup_found = True
                    break
            if not dup_found:
                deduped.append(cand)

        # 4. Rank by relevance * configurable tier weight (final_rank_score descending)
        ranked = sorted(deduped, key=lambda x: x.final_rank_score, reverse=True)

        # 5. Module guarantee: ensure at least one chunk for each detected question module if available
        selected_chunks: List[PackedChunk] = []
        covered_mods: Set[str] = set()

        for q_mod in detected_modules:
            best_mod_cand = next(
                (item for item in ranked if item.module == q_mod and item not in selected_chunks),
                None
            )
            if best_mod_cand:
                selected_chunks.append(best_mod_cand)
                covered_mods.add(q_mod)

        for item in ranked:
            if item not in selected_chunks:
                selected_chunks.append(item)
                if item.module in detected_modules:
                    covered_mods.add(item.module)

        # 6. Fit within dynamic token budget
        packed_list: List[PackedChunk] = []
        packed_blocks: List[str] = []
        current_tokens = 0

        for chunk_item in selected_chunks:
            block = chunk_item.format_chunk()
            block_tokens = self._estimate_tokens(block)
            if current_tokens + block_tokens > dynamic_budget and packed_list:
                break
            packed_list.append(chunk_item)
            packed_blocks.append(block)
            current_tokens += block_tokens

        packed_text = "\n\n".join(packed_blocks)
        uncovered_mods = [m for m in detected_modules if m not in covered_mods]

        return ContextPackingResult(
            packed_chunks=packed_list,
            packed_text=packed_text,
            detected_question_modules=detected_modules,
            covered_question_modules=list(covered_mods),
            uncovered_question_modules=uncovered_mods,
            is_insufficient=False,
            top_score=top_score,
            closest_sources=closest_sources,
            total_estimated_tokens=current_tokens,
            token_budget=dynamic_budget
        )


context_packing_service = ContextPackingService()
