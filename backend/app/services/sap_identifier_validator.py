"""
Claim-level validation of SAP technical identifiers against retrieved evidence.

The validator answers a narrower question than "does this identifier exist?":
it checks whether the *specific claim made about* a transaction, table, field,
navigation path, report, API or SAP Note is established by a retrieved passage.

Design rules (enforced here, relied on by grounding_service):
- An identifier that is absent from the retrieved evidence is "unverified", never
  "invalid": the knowledge base is not a complete catalogue of SAP objects.
- A transaction that exists does not support every operation; the operation and
  its object must appear together with the identifier in the evidence.
- A field's meaning is never inferred from its name; the scope stated by the
  evidence (table, organizational level, process) bounds what may be claimed.
- Navigation paths must appear, in order, in a single evidence passage.
- Direct database edits are never accepted as a normal maintenance procedure.
- The curated entity registry only shows that an identifier is a known SAP object;
  it is never treated as evidence for a claim.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.app.services.sap_entity_service import sap_entity_service

# ---------------------------------------------------------------------------
# Identifier extraction
# ---------------------------------------------------------------------------

# Uppercase transaction/table-shaped tokens: XK02, FD02, KNB1, BUT000, FKLOCK2, OX18, F110.
_CODE_TOKEN = re.compile(r"(?<![A-Za-z0-9_/-])([A-Z]{1,6}[0-9]{1,3}[A-Z]?)(?![A-Za-z0-9_])")
# Underscore identifiers: CVP_XBLCK_B, FKKBIX_BIT_MON, BAPI_BUPA_CENTRAL_CHANGE.
_UNDERSCORE_TOKEN = re.compile(r"(?<![A-Za-z0-9_/])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_])")
# Namespace objects: /1FE/BIT_CREATE.
_NAMESPACE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(/[A-Z0-9]{2,}/[A-Z0-9_]+)", re.IGNORECASE)
# TABLE-FIELD notation: KNB1-SPERR.
_TABLE_FIELD_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{2,15})-([A-Z][A-Z0-9_]{2,29})(?![A-Za-z0-9_])")
# Explicitly typed mentions, including short codes such as "transaction BP".
_TYPED_MENTION = re.compile(
    r"\b(transaction(?:\s+code)?|t-?code|tcode|database\s+table|table|field|report|program|bapi|function\s+module)\s+"
    r"[\"'`(]?([A-Za-z][A-Za-z0-9_/]{1,39})",
    re.IGNORECASE,
)
_SAP_NOTE = re.compile(r"\b(?:SAP\s+)?(?:Note|KBA)s?\s*(?:#|no\.?|number)?\s*(\d{6,7})\b", re.IGNORECASE)
_PATH_SEPARATOR = re.compile(r"\s*(?:->|→|=>|>>|›|\s>\s)\s*")

# Shapes that look like codes but are standards, releases, metrics or prose.
_EXCLUDED_CODES = {
    "IFRS15", "IFRS16", "ASC606", "SHA256", "SHA1", "MD5", "UTF8", "UTF16", "E2E", "B2B", "B2C",
    "P10", "P50", "P90", "P95", "P99", "COVID19", "HTTP2", "HTTP200", "HTTP400", "HTTP404", "HTTP500",
    "OAUTH2", "TLS12", "TLS13", "IPV4", "IPV6", "S4H", "ED1", "GDPR", "ILM", "IMG", "SAP", "ECC6", "BW4",
}
_EXCLUDED_CODE_PREFIX = re.compile(
    r"^(?:SP|SPS|FPS|EHP|TOP|STEP|PHASE|LEVEL|TIER|WAVE|SPRINT|ROUND|CASE|TEST|ITEM|FY|CW|KW|OP|NW|ISO|RFC)\d",
)
_EXCLUDED_UNDERSCORE = {"SAP_ALL", "SAP_NEW"}
_NOT_IDENTIFIER_WORDS = {
    "the", "a", "an", "this", "that", "these", "those", "data", "code", "codes", "is", "are", "to", "in",
    "and", "or", "for", "with", "level", "settings", "maintenance", "view", "views", "entries", "entry",
}

IDENTIFIER_TYPE_HINTS = (
    ("transaction", re.compile(r"\b(transaction(?:\s+code)?|t-?code|tcode)\s*$", re.IGNORECASE),
     re.compile(r"^\s*(transaction|t-?code|tcode)\b", re.IGNORECASE)),
    ("table", re.compile(r"\b(database\s+table|table)\s*$", re.IGNORECASE),
     re.compile(r"^\s*(database\s+)?table\b", re.IGNORECASE)),
    ("field", re.compile(r"\b(field|flag|indicator)\s*$", re.IGNORECASE),
     re.compile(r"^\s*(field|flag|indicator)\b", re.IGNORECASE)),
    ("report", re.compile(r"\b(report|program)\s*$", re.IGNORECASE),
     re.compile(r"^\s*(report|program)\b", re.IGNORECASE)),
    ("api", re.compile(r"\b(bapi|function\s+module|api)\s*$", re.IGNORECASE),
     re.compile(r"^\s*(bapi|function\s+module|api)\b", re.IGNORECASE)),
)


@dataclass
class Identifier:
    value: str          # canonical uppercase form
    id_type: str        # transaction | table | field | table_field | report | api | sap_note | identifier
    start: int = 0
    end: int = 0


def _typed_from_context(text: str, start: int, end: int) -> Optional[str]:
    before = text[max(0, start - 30):start]
    after = text[end:end + 25]
    for id_type, before_rx, after_rx in IDENTIFIER_TYPE_HINTS:
        if before_rx.search(before) or after_rx.search(after):
            return id_type
    return None


def _is_excluded_code(token: str) -> bool:
    return token in _EXCLUDED_CODES or bool(_EXCLUDED_CODE_PREFIX.match(token)) or len(token) < 3


def extract_identifiers(text: str) -> List[Identifier]:
    """Extract SAP technical identifiers with a best-effort type from local context."""
    if not text:
        return []
    found: Dict[str, Identifier] = {}

    def add(value: str, start: int, end: int, default_type: str) -> None:
        canonical = value.strip().upper()
        if not canonical or canonical.lower() in _NOT_IDENTIFIER_WORDS:
            return
        id_type = _typed_from_context(text, start, end) or default_type
        if id_type == "identifier":
            entity = sap_entity_service.lookup_entity(canonical)
            if entity and entity.get("type") in ("tcode", "table"):
                id_type = "transaction" if entity["type"] == "tcode" else "table"
        if canonical.startswith("BAPI_"):
            id_type = "api"
        existing = found.get(canonical)
        if existing is None or (existing.id_type == "identifier" and id_type != "identifier"):
            found[canonical] = Identifier(canonical, id_type, start, end)

    for m in _TABLE_FIELD_TOKEN.finditer(text):
        table, fld = m.group(1), m.group(2)
        if f"{table}-{fld}" in {"FI-CA", "FI-GL", "FI-AR", "FI-AP"}:
            continue
        add(f"{table}-{fld}", m.start(), m.end(), "table_field")
    for m in _NAMESPACE_TOKEN.finditer(text):
        add(m.group(1), m.start(1), m.end(1), "identifier")
    for m in _UNDERSCORE_TOKEN.finditer(text):
        if m.group(1) not in _EXCLUDED_UNDERSCORE:
            add(m.group(1), m.start(1), m.end(1), "identifier")
    for m in _CODE_TOKEN.finditer(text):
        if not _is_excluded_code(m.group(1)):
            add(m.group(1), m.start(1), m.end(1), "identifier")
    for m in _TYPED_MENTION.finditer(text):
        kind, token = m.group(1).lower(), m.group(2)
        if token.lower() in _NOT_IDENTIFIER_WORDS:
            continue
        # Typed mentions only add identifiers written as codes ("transaction BP"),
        # never ordinary words ("table of contents", "transaction data").
        if not (token.isupper() or re.search(r"[_/0-9]", token)):
            continue
        id_type = (
            "transaction" if kind.startswith(("transaction", "t-code", "tcode", "t code"))
            else "table" if "table" in kind
            else "field" if kind == "field"
            else "report" if kind in ("report", "program")
            else "api"
        )
        canonical = token.upper()
        if canonical not in found or found[canonical].id_type == "identifier":
            found[canonical] = Identifier(canonical, id_type, m.start(2), m.end(2))
    for m in _SAP_NOTE.finditer(text):
        key = f"NOTE {m.group(1)}"
        found[key] = Identifier(key, "sap_note", m.start(), m.end())
    return sorted(found.values(), key=lambda ident: ident.start)


def extract_navigation_paths(text: str) -> List[List[str]]:
    """Return arrow-separated menu/IMG paths with at least three segments."""
    paths: List[List[str]] = []
    for line in re.split(r"[\n;]", text or ""):
        if not _PATH_SEPARATOR.search(line):
            continue
        segments = [_strip_lead_in(s.strip(" .:*`\"'()[]")) for s in _PATH_SEPARATOR.split(line)]
        segments = [s for s in segments if s and len(s) <= 90]
        if len(segments) >= 3:
            paths.append(segments)
    return paths


def _strip_lead_in(segment: str) -> str:
    # "Go to SPRO" / "Navigate to Logistics" -> keep the menu node only.
    segment = re.sub(
        r"^.*?\b(?:[Gg]o\s+to|[Nn]avigate\s+to|[Cc]hoose|[Ss]elect|[Oo]pen|[Ff]ollow|[Pp]ath:?|[Mm]enu:?|via|under)\s+(?=[A-Z])",
        "", segment,
    )
    segment = re.sub(r"^[Ii]n\s+(?=[A-Z])", "", segment)
    segment = re.sub(r"\s*\[E\d+(?:\s*,\s*E\d+)*\]", "", segment)
    segment = re.sub(r"\s*\((?:transaction\s+)?[A-Z0-9_]{2,}\)\s*$", "", segment)
    return segment.strip(" .:,")


# ---------------------------------------------------------------------------
# Claim analysis helpers
# ---------------------------------------------------------------------------

_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "via", "using", "by", "from", "and", "or",
    "is", "are", "be", "been", "can", "could", "should", "must", "will", "would", "may", "might", "it", "its",
    "this", "that", "these", "those", "you", "your", "we", "our", "then", "there", "which", "when", "where",
    "as", "into", "use", "used", "transaction", "table", "field", "sap", "s/4hana", "through", "also", "any",
    "not", "only", "if", "has", "have", "was", "were", "do", "does", "done", "per", "all", "such",
}
_OBJECT_STOP_AT = {
    "via", "using", "with", "through", "by", "in", "on", "at", "from", "for", "so", "and", "then", "which",
    "that", "where", "when", "because", "if", "once", "after", "before", "transaction", "tcode", "t-code", "under",
}
_AUXILIARIES = {"can", "be", "is", "are", "was", "were", "should", "must", "will", "may", "been", "being", "to"}

OPERATION_FAMILIES: Dict[str, re.Pattern] = {
    "unblock": re.compile(r"\b(unblock\w*|unlock\w*|remov\w+|lift\w*|delet\w+|reset\w*|deactivat\w+|undo\w*|"
                          r"clear(?:s|ed|ing)?(?=\s+(?:the\s+)?(?:[\w-]+\s+){0,3}(?:block|lock|flag|indicator)s?\b))\b"),
    "maintain": re.compile(r"\b(maintain\w*|chang\w+|edit\w*|modif\w+|updat\w+|adjust\w*)\b"),
    "create": re.compile(r"\b(creat\w+|generat\w+|activat\w+)\b"),
    "display": re.compile(r"\b(display\w*|view\w*|see|show\w*|inspect\w*|identif\w+|listed|listing|monitor\w*|"
                          r"look\s+up|find|evaluat\w+)\b"),
}
_RELEASE_VERB = re.compile(r"\breleas\w+\b")
_BLOCK_NOUN = re.compile(r"\b(block|blocks|lock|locks|restriction|restrictions)\b")
_INSTRUCTION = re.compile(
    r"\b(use|using|via|run|execute|go\s+to|navigate|call|open|launch|with\s+transaction|in\s+transaction)\b"
    r"|^\s*(?:to\s+\w+[^,]*,\s*)?(?:run|execute|open|go|navigate|enter|call|start|choose|select|set|clear|"
    r"remove|maintain|change)\b",
    re.IGNORECASE,
)
_MEANING_VERB = re.compile(
    r"\b(indicates?|represents?|means|denotes?|signif(?:y|ies)|flags?|marks?|stores?|controls?|holds?|is\s+the|"
    r"is\s+a|acts\s+as|serves\s+as|determines?|is\s+set\s+when|when\s+set|is\s+blocked\s+when)\b",
    re.IGNORECASE,
)
# Scope words that widen what a field or block means beyond what a passage states.
_GENERALIZATION = re.compile(
    r"\b(universal\w*|general|generic|global\w*|central|overall|every|operational|complete|entire|whole|"
    r"all\s+(?:processes|transactions|postings|business|operations|activities|areas|organizational)|"
    r"any\s+(?:process|transaction|posting|operation|activity)|(?:business\s+partner|bp)[-\s]level|"
    r"across\s+(?:all|the\s+(?:system|company)))\b",
    re.IGNORECASE,
)
_AVAILABILITY_NEGATION = re.compile(
    r"\b(not\s+available|no\s+longer\s+(?:available|supported|used)|not\s+supported|obsolete|deprecated|"
    r"replaced\s+by|cannot\s+be\s+used|not\s+be\s+used|are\s+not\s+used|is\s+not\s+used|redirect\w*\s+to)\b",
    re.IGNORECASE,
)
# "The simplification list states that ..." - a claim about what a source says.
_ATTRIBUTION = re.compile(
    r"\b(states?\s+that|according\s+to|documents?\s+that|lists?\s+that|notes?\s+that|"
    r"(?:source|passage|documentation|guide|list|note)\s+(?:says|states|describes|indicates|documents))\b",
    re.IGNORECASE,
)
_ECC_SCOPE = re.compile(r"\b(ecc|business\s+suite|r/3|erp\s+6(?:\.0)?)\b", re.IGNORECASE)
_S4_SCOPE = re.compile(r"\bs/?4\s?hana\b|\bs4h\b", re.IGNORECASE)
_DIRECT_DB_WRITE = re.compile(
    r"(\b(?:update|modify|edit|overwrite|change|set|clear|reset|delete|blank\s+out|untick|uncheck|remove)\b[^.\n]{0,70}"
    r"\b(?:directly\s+in\s+(?:the\s+)?(?:database|table)|directly|in\s+the\s+database|database\s+table|"
    r"via\s+se16n?|with\s+se16n?|using\s+se16n?|in\s+se16n?|via\s+sql|with\s+sql|at\s+(?:the\s+)?database\s+level)\b)"
    r"|(\bse16n?\b[^.\n]{0,80}\b(?:edit|change|modify|update|set|clear|reset|delete|remove|untick|uncheck)\w*)"
    r"|(&sap_edit)|(\bupdate\s+[a-z0-9_]+\s+set\b)|(\bdebug\w*\b[^.\n]{0,60}\b(?:change|modify|overwrite)\b[^.\n]{0,30}\bvalue)",
    re.IGNORECASE,
)
_NEGATED_ADVICE = re.compile(
    r"\b(do\s+not|don't|never|avoid|must\s+not|should\s+not|shouldn't|not\s+recommended|not\s+a\s+supported|"
    r"is\s+not\s+(?:a\s+)?(?:supported|recommended)|instead\s+of|rather\s+than|unsupported)\b",
    re.IGNORECASE,
)
LIMITATION_STATEMENT = re.compile(
    r"\b(not\s+verified|unverified|could\s+not\s+be\s+(?:verified|confirmed|established)|"
    r"cannot\s+(?:be\s+)?(?:verified|confirmed|established)|could\s+not\s+(?:confirm|verify|establish)|"
    r"not\s+(?:established|confirmed|documented)\s+(?:by|in)|"
    r"(?:does|do)\s+not\s+(?:establish|confirm|document|state|specify|cover|show)|no\s+(?:retrieved\s+)?evidence|"
    r"unresolved|requires?\s+(?:confirmation|verification)|to\s+be\s+confirmed|not\s+covered\s+by|"
    r"evidence\s+(?:does\s+not|doesn't)|is\s+not\s+(?:stated|specified)\s+(?:in|by)|"
    r"not\s+(?:found|located)\s+in\s+the\s+(?:retrieved|available|internal))",
    re.IGNORECASE,
)


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9_/-]*", (text or "").lower())


def _norm(token: str) -> str:
    # Plural noun -> singular only. "-ed" forms stay distinct so "blocked supplier"
    # (adjective) is not confused with "the block" (the object being removed).
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def content_terms(text: str, exclude: Iterable[str] = ()) -> List[str]:
    excluded = {e.lower() for e in exclude}
    return [_norm(t) for t in _tokens(text) if t not in _STOP and t not in excluded and len(t) > 2]


def _operation_family(text: str, anchor: Optional[int] = None) -> Optional[Tuple[str, re.Match]]:
    """Operation verb of the clause; with an anchor, the verb nearest the identifier wins
    (so "the simplification list states ... removed via XK02" resolves to "removed")."""
    lowered = (text or "").lower()

    def distance(m: re.Match) -> int:
        return m.start() if anchor is None else min(abs(m.start() - anchor), abs(m.end() - anchor))

    best: Optional[Tuple[str, re.Match]] = None
    for family, rx in OPERATION_FAMILIES.items():
        for m in rx.finditer(lowered):
            if best is None or distance(m) < distance(best[1]):
                best = (family, m)
    if _BLOCK_NOUN.search(lowered):
        for rel in _RELEASE_VERB.finditer(lowered):
            if best is None or distance(rel) < distance(best[1]):
                best = ("unblock", rel)
    return best


def _object_terms(text: str, verb_match: re.Match, identifiers: Sequence[str]) -> List[str]:
    lowered = text.lower()
    ids = {i.lower() for i in identifiers}
    terms: List[str] = []
    for tok in _tokens(lowered[verb_match.end():])[:9]:
        if tok in _OBJECT_STOP_AT or tok in ids:
            break
        if tok in _STOP or len(tok) <= 2:
            continue
        terms.append(_norm(tok))
    if not terms:
        # Passive voice: "the block can be removed via ..."
        for tok in reversed(_tokens(lowered[:verb_match.start()])[-6:]):
            if tok in ids or tok in _OBJECT_STOP_AT:
                break
            if tok in _AUXILIARIES or tok in _STOP or len(tok) <= 2:
                continue
            terms.insert(0, _norm(tok))
            if len(terms) >= 4:
                break
    return terms[:5]


# ---------------------------------------------------------------------------
# Evidence windows
# ---------------------------------------------------------------------------

@dataclass
class EvidenceWindow:
    passage_index: int
    evidence_id: str
    text: str
    source_type: str


def passage_text(passage: Dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(passage.get("chunk_text") or passage.get("snippet") or "")).strip()


def is_gap(passage: Dict[str, Any]) -> bool:
    return bool(passage.get("retrieval_gap")) or passage.get("source_type") == "retrieval_gap"


def evidence_id_for(passage: Dict[str, Any], index: int) -> str:
    return str(passage.get("evidence_id") or f"P{index + 1}")


def identifier_windows(identifier: str, passages: Sequence[Dict[str, Any]], radius: int = 260) -> List[EvidenceWindow]:
    """Text around each mention of `identifier`, bounded to the passage that contains it."""
    lookup = identifier.split(" ", 1)[1] if identifier.startswith("NOTE ") else identifier
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(lookup)}(?![A-Za-z0-9_])", re.IGNORECASE)
    windows: List[EvidenceWindow] = []
    for idx, passage in enumerate(passages):
        if is_gap(passage):
            continue
        text = passage_text(passage)
        for m in pattern.finditer(text):
            windows.append(EvidenceWindow(
                passage_index=idx,
                evidence_id=evidence_id_for(passage, idx),
                text=text[max(0, m.start() - radius):min(len(text), m.end() + radius)],
                source_type=str(passage.get("source_type") or ("web" if passage.get("url") else "knowledge_base")),
            ))
    return windows


def _clause_around(window: str, identifier: str, span: int = 160) -> str:
    """The sentence containing the identifier inside a window (falls back to +/- span chars)."""
    m = re.search(rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])", window, re.IGNORECASE)
    if not m:
        return window
    left = max(window.rfind(". ", 0, m.start()), window.rfind("? ", 0, m.start()), window.rfind("! ", 0, m.start()))
    left = left + 2 if left >= 0 and m.start() - left < 400 else max(0, m.start() - span)
    right_candidates = [i for i in (window.find(". ", m.end()), window.find("? ", m.end())) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else min(len(window), m.end() + span)
    return window[left:right]


def release_context(*texts: str) -> Dict[str, bool]:
    joined = " ".join(t for t in texts if t)
    return {"s4hana": bool(_S4_SCOPE.search(joined)), "ecc": bool(_ECC_SCOPE.search(joined))}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

CRITICAL_STATUSES = {
    "contradicted",
    "unsafe_procedure",
    "operation_not_evidenced",
    "unverified_procedure",
    "overgeneralized_meaning",
    "meaning_not_evidenced",
    "unverified_path",
}
# Statuses that do not make the sentence unsupported on their own.
NON_FAILING_STATUSES = {"verified", "qualified", "weakly_supported"}


@dataclass
class TechnicalCheck:
    claim: str
    identifier: str
    identifier_type: str
    claim_type: str          # mention | operation | field_meaning | availability | navigation_path | direct_db_update
    status: str
    reason: str
    evidence_ids: List[str] = field(default_factory=list)
    registry_known: bool = False
    operation: Optional[str] = None
    critical: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _registry_known(identifier: str) -> bool:
    try:
        return sap_entity_service.is_known_sap_identifier(identifier.lower())
    except Exception:
        return False


class SAPIdentifierValidator:
    """Validates the claim made about each technical identifier in a sentence."""

    @staticmethod
    def is_limitation_statement(sentence: str) -> bool:
        return bool(LIMITATION_STATEMENT.search(sentence or ""))

    @staticmethod
    def detect_direct_db_update(sentence: str) -> Optional[str]:
        m = _DIRECT_DB_WRITE.search(sentence or "")
        if not m or _NEGATED_ADVICE.search(sentence):
            return None
        return m.group(0)

    def validate_sentence(self, sentence: str, passages: Sequence[Dict[str, Any]], *, query: str = "") -> List[TechnicalCheck]:
        """Return one check per technical claim found in `sentence`."""
        clean = re.sub(r"\s*\[E\d+(?:\s*,\s*E\d+)*\]", "", sentence or "").strip()
        if not clean:
            return []
        limitation = self.is_limitation_statement(clean)
        checks: List[TechnicalCheck] = []

        db_write = self.detect_direct_db_update(clean)
        if db_write and not limitation:
            checks.append(TechnicalCheck(
                claim=clean, identifier=db_write[:60], identifier_type="procedure", claim_type="direct_db_update",
                status="unsafe_procedure", critical=True,
                reason="Direct database modification is presented as a procedure; supported maintenance must use "
                       "the application transaction or API documented for the object.",
            ))
        for path in extract_navigation_paths(clean):
            checks.append(self._check_path(clean, path, passages, limitation))

        identifiers = extract_identifiers(clean)
        id_values = [i.value for i in identifiers]
        for ident in identifiers:
            checks.append(self._check_identifier(clean, ident, id_values, passages, query=query, limitation=limitation))
        return checks

    # -- navigation paths --------------------------------------------------------------

    @staticmethod
    def _check_path(sentence: str, path: List[str], passages: Sequence[Dict[str, Any]], limitation: bool) -> TechnicalCheck:
        label = " -> ".join(path)
        best_hits, best_id = 0, None
        for idx, passage in enumerate(passages):
            if is_gap(passage):
                continue
            text = passage_text(passage).lower()
            position, hits = 0, 0
            for segment in path:
                seg = re.sub(r"\s+", " ", segment.lower()).strip()
                found_at = text.find(seg, position)
                if found_at < 0:
                    break
                hits += 1
                position = found_at + len(seg)
            if hits > best_hits:
                best_hits, best_id = hits, evidence_id_for(passage, idx)
        if best_hits == len(path):
            return TechnicalCheck(sentence, label, "img_path", "navigation_path", "verified",
                                  "Every path segment appears, in order, in one evidence passage.", [best_id])
        if limitation:
            return TechnicalCheck(sentence, label, "img_path", "navigation_path", "qualified",
                                  "Path is explicitly presented as unverified.", [best_id] if best_id else [])
        return TechnicalCheck(
            sentence, label, "img_path", "navigation_path", "unverified_path", critical=True,
            reason=f"Only {best_hits} of {len(path)} path segments were found in order in a single passage; "
                   "the navigation path is not confirmed by the evidence.",
            evidence_ids=[best_id] if best_id and best_hits else [],
        )

    # -- identifiers ---------------------------------------------------------------------

    def _check_identifier(self, sentence: str, ident: Identifier, all_ids: Sequence[str],
                          passages: Sequence[Dict[str, Any]], *, query: str, limitation: bool) -> TechnicalCheck:
        identifier = ident.value
        lookup = identifier.split("-", 1)[1] if ident.id_type == "table_field" else identifier
        windows = identifier_windows(lookup, passages)
        if ident.id_type == "table_field":
            table = identifier.split("-", 1)[0]
            windows = [w for w in windows if re.search(rf"\b{re.escape(table)}\b", w.text, re.IGNORECASE)] or windows
        known = _registry_known(identifier)
        window_ids = sorted({w.evidence_id for w in windows})

        def result(claim_type: str, status: str, reason: str, ids: Optional[List[str]] = None,
                   operation: Optional[str] = None) -> TechnicalCheck:
            return TechnicalCheck(
                claim=sentence, identifier=identifier, identifier_type=ident.id_type, claim_type=claim_type,
                status=status, reason=reason, evidence_ids=ids if ids is not None else window_ids,
                registry_known=known, operation=operation, critical=status in CRITICAL_STATUSES,
            )

        if limitation:
            return result("mention", "qualified", "Sentence explicitly qualifies this identifier as unverified or unresolved.")
        if _NEGATED_ADVICE.search(sentence) and not _AVAILABILITY_NEGATION.search(sentence):
            return result("mention", "qualified", "Sentence advises against this action; it is not a procedural claim.")

        # 1. Availability statements ("XK02 is not available in S/4HANA").
        if _AVAILABILITY_NEGATION.search(sentence):
            agrees = [w for w in windows if _AVAILABILITY_NEGATION.search(w.text)]
            if agrees:
                return result("availability", "verified", "Evidence states the same availability restriction.",
                              sorted({w.evidence_id for w in agrees}))
            return result("availability", "unverified", "Availability/obsolescence claim is not stated by the retrieved evidence.")

        op = _operation_family(sentence, anchor=ident.start)
        is_instruction = bool(_INSTRUCTION.search(sentence))
        contradiction = self._availability_conflict(sentence, windows, query)

        # 2. Operation claims ("use XK02 to remove the block").
        if op and (is_instruction or ident.id_type == "transaction"):
            family, verb = op
            objects = _object_terms(sentence, verb, all_ids)
            supporting = self._operation_support(lookup, family, objects, windows)
            if contradiction and supporting and _ATTRIBUTION.search(sentence):
                return result("operation", "verified",
                              "Statement is attributed to the source that documents it; the conflicting availability "
                              "statement must be reported separately.",
                              sorted({w.evidence_id for w in supporting}), operation=family)
            if contradiction and supporting:
                return result("operation", "conflicting_evidence",
                              "One passage documents this operation, another states the identifier is not available "
                              "in the applicable release; the claim must be qualified by release.",
                              sorted({w.evidence_id for w in supporting + contradiction}), operation=family)
            if contradiction:
                return result("operation", "contradicted",
                              f"Evidence states {identifier} is not available/obsolete in the applicable release, but the "
                              "answer recommends it without restricting the claim to a release where it applies.",
                              sorted({w.evidence_id for w in contradiction}), operation=family)
            if supporting:
                return result("operation", "verified",
                              f"Evidence documents '{family}' for {identifier} with the same object ({', '.join(objects) or 'n/a'}).",
                              sorted({w.evidence_id for w in supporting}), operation=family)
            if windows:
                said = " | ".join(_clause_around(w.text, lookup)[:180] for w in windows[:2])
                return result("operation", "operation_not_evidenced",
                              f"{identifier} appears in the evidence, but not for the claimed operation "
                              f"('{family}': {' '.join(objects) or 'unspecified object'}). Evidence context: {said}",
                              operation=family)
            reason = (f"{identifier} does not appear in the retrieved evidence, so the claimed operation "
                      f"('{family}': {' '.join(objects) or 'unspecified object'}) is unverified. "
                      "This does not mean the identifier is invalid.")
            if known:
                reason += " It is a known SAP object, but existence does not establish support for this operation."
            return result("operation", "unverified_procedure", reason, [], operation=family)

        if contradiction and is_instruction:
            return result("operation", "contradicted",
                          f"Evidence states {identifier} is not available/obsolete in the applicable release.",
                          sorted({w.evidence_id for w in contradiction}))

        # 3. Field/indicator meaning claims: scope must not exceed what the evidence states.
        is_field = ident.id_type in ("field", "table_field") or ("_" in identifier and ident.id_type == "identifier")
        if is_field and _MEANING_VERB.search(sentence):
            if not windows:
                return result("field_meaning", "meaning_not_evidenced",
                              f"No evidence describes {identifier}; a field's meaning cannot be inferred from its name.")
            claim_general = {g.lower() for g in _GENERALIZATION.findall(sentence)}
            evidence_general = set()
            for w in windows:
                evidence_general |= {g.lower() for g in _GENERALIZATION.findall(_clause_around(w.text, lookup, 220))}
            overreach = sorted(claim_general - evidence_general)
            if overreach:
                scope = " | ".join(_clause_around(w.text, lookup, 220)[:220] for w in windows[:2])
                return result("field_meaning", "overgeneralized_meaning",
                              f"The answer widens {identifier} to '{', '.join(overreach)}', but the evidence only "
                              f"establishes it in this scope: {scope}")
            overlap = self._overlap(sentence, windows, exclude=[identifier, lookup])
            if overlap >= 0.34:
                return result("field_meaning", "verified",
                              f"Evidence describes {identifier} in the claimed sense (overlap {overlap:.2f}).")
            return result("field_meaning", "meaning_not_evidenced",
                          f"Evidence mentions {identifier}, but not with the claimed meaning (overlap {overlap:.2f}).")

        # 4. Plain mentions / descriptive claims.
        if not windows:
            reason = f"{identifier} is not present in the retrieved evidence; the statement is unverified (not invalid)."
            if known:
                reason += " The identifier is a known SAP object, but its role in this statement is not evidenced."
            return result("mention", "unverified_procedure" if is_instruction else "unverified", reason, [])
        overlap = self._overlap(sentence, windows, exclude=[identifier, lookup])
        if overlap >= 0.30:
            return result("mention", "verified", f"Evidence around {identifier} supports the statement (overlap {overlap:.2f}).")
        return result("mention", "weakly_supported",
                      f"{identifier} appears in the evidence, but the statement is only weakly supported (overlap {overlap:.2f}).")

    @staticmethod
    def _overlap(sentence: str, windows: Sequence[EvidenceWindow], exclude: Sequence[str]) -> float:
        terms = content_terms(sentence, exclude=exclude)
        if not terms:
            return 1.0
        best = 0.0
        for w in windows:
            window_terms = set(content_terms(w.text))
            best = max(best, sum(1 for t in terms if t in window_terms) / len(terms))
        return best

    @staticmethod
    def _operation_support(identifier: str, family: str, objects: Sequence[str],
                           windows: Sequence[EvidenceWindow]) -> List[EvidenceWindow]:
        supported = []
        rx = OPERATION_FAMILIES[family]
        for w in windows:
            clause = _clause_around(w.text, identifier, span=220).lower()
            verb_present = bool(rx.search(clause)) or (
                family == "unblock" and bool(_RELEASE_VERB.search(clause)) and bool(_BLOCK_NOUN.search(clause))
            )
            if not verb_present:
                continue
            if objects:
                clause_terms = {_norm(t) for t in _tokens(clause)}
                matched = sum(1 for o in objects if o in clause_terms)
                needed = len(objects) if len(objects) <= 3 else int(len(objects) * 0.75 + 0.5)
                if matched < needed:
                    continue
            supported.append(w)
        return supported

    @staticmethod
    def _availability_conflict(sentence: str, windows: Sequence[EvidenceWindow], query: str) -> List[EvidenceWindow]:
        """Windows saying the identifier is unavailable in a release the claim does not exclude."""
        claim_scope = release_context(sentence)
        query_scope = release_context(query)
        if claim_scope["ecc"] and not claim_scope["s4hana"]:
            return []   # claim explicitly restricted to ECC / Business Suite
        if query_scope["ecc"] and not query_scope["s4hana"]:
            return []   # user asked about ECC; S/4HANA unavailability is not a contradiction
        return [w for w in windows if _AVAILABILITY_NEGATION.search(w.text)]

    # -- cross-source comparison ---------------------------------------------------------

    def detect_evidence_conflicts(self, passages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identifiers that one passage documents for use while another declares them unavailable."""
        identifiers = set()
        for passage in passages:
            if not is_gap(passage):
                identifiers |= {i.value for i in extract_identifiers(passage_text(passage)) if i.id_type != "sap_note"}
        conflicts: List[Dict[str, Any]] = []
        for identifier in sorted(identifiers):
            windows = identifier_windows(identifier, passages)
            # Whole window: table-style lists put "not available" far from the identifier.
            negative = [w for w in windows if _AVAILABILITY_NEGATION.search(w.text)]
            positive = [w for w in windows if w not in negative and _operation_family(_clause_around(w.text, identifier, 220))]
            if negative and positive:
                conflicts.append({
                    "identifier": identifier,
                    "kind": "availability_vs_documented_use",
                    "unavailable_in": sorted({w.evidence_id for w in negative}),
                    "documented_use_in": sorted({w.evidence_id for w in positive}),
                    "cross_source": len({w.source_type for w in negative + positive}) > 1,
                })
        return conflicts


sap_identifier_validator = SAPIdentifierValidator()
