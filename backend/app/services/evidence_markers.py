"""
Inline evidence markers ([E1], [E2, E4]) that tie each answer claim to the passage
supporting it.

Markers are opaque IDs, not source names, so they can be validated claim-by-claim.
Users who are not allowed to see sources (non-admins) receive answers with the
markers removed; admins receive them together with citations carrying a matching
`ref`.
"""

import re
from typing import Any, Dict, List, Sequence, Set

# Some models wrap marker IDs in zero-width characters ("[​E2​]"); they are still markers.
_ZW = "[​‌‍⁠﻿]*"
MARKER_PATTERN = re.compile(rf"\s?\[{_ZW}(E\d{{1,3}}(?:{_ZW}\s*,\s*{_ZW}E\d{{1,3}})*){_ZW}\]")
_ID_PATTERN = re.compile(r"E\d{1,3}")
_FULL_MARKER = re.compile(rf"\[{_ZW}E\d{{1,3}}(?:{_ZW}\s*,\s*{_ZW}E\d{{1,3}})*{_ZW}\]")
_MARKER_PREFIX = re.compile(rf"\[{_ZW}(?:E\d{{0,3}}{_ZW}(?:\s*,\s*{_ZW}(?:E\d{{0,3}}{_ZW})?)*)?")


def is_citable(passage: Dict[str, Any]) -> bool:
    return not (passage.get("retrieval_gap") or passage.get("source_type") == "retrieval_gap")


def assign_evidence_ids(passages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Number citable passages E1..En in prompt order (retrieval-gap markers get no ID)."""
    counter = 0
    for passage in passages:
        if is_citable(passage):
            counter += 1
            passage["evidence_id"] = f"E{counter}"
        else:
            passage.pop("evidence_id", None)
    return list(passages)


def valid_ids(passages: Sequence[Dict[str, Any]]) -> Set[str]:
    return {str(p["evidence_id"]) for p in passages if p.get("evidence_id")}


def extract_marker_ids(text: str) -> List[str]:
    ids: List[str] = []
    for m in MARKER_PATTERN.finditer(text or ""):
        ids.extend(_ID_PATTERN.findall(m.group(1)))
    return list(dict.fromkeys(ids))


def strip_markers(text: str) -> str:
    """Remove all evidence markers (for users who may not see sources)."""
    cleaned = MARKER_PATTERN.sub("", text or "")
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)


def remove_invalid_markers(text: str, allowed: Set[str]) -> str:
    """Drop marker IDs that do not refer to supplied evidence (never keep an invented citation)."""
    def repl(m: re.Match) -> str:
        kept = [i for i in _ID_PATTERN.findall(m.group(1)) if i in allowed]
        if not kept:
            return ""
        lead = " " if m.group(0)[:1].isspace() else ""
        return f"{lead}[{', '.join(kept)}]"
    return MARKER_PATTERN.sub(repl, text or "")


class StreamingMarkerStripper:
    """Removes markers from a token stream whose markers may be split across tokens."""

    _MAX_PENDING = 24

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, token: str) -> str:
        out: List[str] = []
        for ch in token or "":
            if self._pending:
                self._pending += ch
                if _FULL_MARKER.fullmatch(self._pending):
                    self._pending = ""
                elif len(self._pending) > self._MAX_PENDING or not _MARKER_PREFIX.fullmatch(self._pending):
                    out.append(self._pending)
                    self._pending = ""
            elif ch == "[":
                self._pending = ch
            else:
                out.append(ch)
        return "".join(out)

    def flush(self) -> str:
        remainder, self._pending = self._pending, ""
        return remainder
