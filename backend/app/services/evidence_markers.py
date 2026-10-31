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
# Legacy source-label markers ([KB_1], [WEB_2], [REPO_3]) from older prompts; never shown to non-admins.
_LEGACY_ID = r"(?:KB|WEB|REPO)_\d{1,4}"
LEGACY_MARKER_PATTERN = re.compile(rf"\s?\[{_ZW}{_LEGACY_ID}{_ZW}\]")
_FULL_LEGACY = re.compile(rf"\[{_ZW}{_LEGACY_ID}{_ZW}\]")
_LEGACY_PREFIX = re.compile(
    rf"\[{_ZW}(?:K(?:B(?:_\d{{0,4}})?)?|W(?:E(?:B(?:_\d{{0,4}})?)?)?|R(?:E(?:P(?:O(?:_\d{{0,4}})?)?)?)?){_ZW}"
)


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
    """Remove all evidence markers, including legacy [KB_n]/[WEB_n]/[REPO_n] (for users who may not see sources)."""
    cleaned = LEGACY_MARKER_PATTERN.sub("", MARKER_PATTERN.sub("", text or ""))
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

    @staticmethod
    def _is_complete(pending: str) -> bool:
        return bool(_FULL_MARKER.fullmatch(pending) or _FULL_LEGACY.fullmatch(pending))

    @staticmethod
    def _may_become_marker(pending: str) -> bool:
        return bool(_MARKER_PREFIX.fullmatch(pending) or _LEGACY_PREFIX.fullmatch(pending))

    def feed(self, token: str) -> str:
        out: List[str] = []
        for ch in token or "":
            if self._pending:
                candidate = self._pending + ch
                if self._is_complete(candidate):
                    self._pending = ""
                elif len(candidate) <= self._MAX_PENDING and self._may_become_marker(candidate):
                    self._pending = candidate
                else:
                    # Not a marker: release the held text, and let a "[" start a new candidate
                    # (otherwise "[[E1]" would leak its marker).
                    out.append(self._pending)
                    self._pending = ""
                    if ch == "[":
                        self._pending = ch
                    else:
                        out.append(ch)
            elif ch == "[":
                self._pending = ch
            else:
                out.append(ch)
        return "".join(out)

    def flush(self) -> str:
        remainder, self._pending = self._pending, ""
        return remainder
