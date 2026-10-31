"""
Deterministic safe-degradation for answers that still fail critical validation
after the single repair attempt.

Sentences whose technical claims were contradicted, unsafe, or not established by
evidence are removed; verified content is kept; and the unresolved points are
stated in user-facing language (no source names, scores, or internal details).
The result must be re-verified by the caller before publication.
"""

import re
from typing import Any, Dict, List, Optional, Set

from backend.app.services.evidence_markers import MARKER_PATTERN, remove_invalid_markers

_BULLET = re.compile(r"^(\s*(?:[*\-]|\d+[.)])\s+)")
_HEADING = re.compile(r"^\s*#{1,6}\s")
UNRESOLVED_HEADING = "**Not confirmed by the available SAP documentation**"

_USER_MESSAGES = {
    "contradicted": "`{id}` could not be confirmed for your release: the documentation lists it as not available or obsolete in at least one applicable release.",
    "operation_not_evidenced": "The documentation found does not confirm that `{id}` performs this step, so the step was removed.",
    "unverified_procedure": "Using `{id}` for this step could not be confirmed from the available documentation, so the step was removed.",
    "overgeneralized_meaning": "The meaning of `{id}` as a general block indicator could not be confirmed; the documentation describes it only in a narrower context.",
    "meaning_not_evidenced": "The meaning of `{id}` could not be confirmed from the documentation and was not inferred from its name.",
    "unverified_path": "A menu or configuration path could not be confirmed and was removed.",
    "unsafe_procedure": "Removing a block by editing database tables directly could not be confirmed as a supported procedure, so it was removed; use the maintenance function documented for your block type.",
    "unsupported_effect": "Statements about what happens after removing the block could not be confirmed and were removed.",
}


def _normalize(sentence: str) -> str:
    text = MARKER_PATTERN.sub("", sentence)
    text = _BULLET.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_keep(line: str) -> List[str]:
    # Same boundaries the verifier uses, after moving trailing markers before punctuation.
    line = re.sub(r"([.!?])\s*((?:\[E\d{1,3}(?:\s*,\s*E\d{1,3})*\]\s*)+)", lambda m: f" {m.group(2).strip()}{m.group(1)} ", line)
    return [p for p in re.split(r"(?<=[.!?])\s+", line) if p.strip()]


def _drop_orphan_headings(lines: List[str]) -> List[str]:
    out: List[str] = []
    for i, line in enumerate(lines):
        if _HEADING.match(line):
            following = next((l for l in lines[i + 1:] if l.strip()), None)
            if following is None or _HEADING.match(following):
                continue
        out.append(line)
    return out


def apply_guard(
    answer: str,
    verification: Dict[str, Any],
    *,
    allowed_evidence_ids: Optional[Set[str]] = None,
    clarification_question: Optional[str] = None,
    evidence_needed: Optional[List[str]] = None,
) -> Dict[str, Any]:
    failures = list(verification.get("critical_failures") or [])
    contradicted = set(verification.get("contradicted_claims") or [])
    failing_claims = {_normalize(f["claim"]) for f in failures if f.get("claim")} | {_normalize(c) for c in contradicted}
    if not failing_claims:
        return {"answer": answer, "applied": False, "removed_claims": []}

    removed: List[str] = []
    kept_lines: List[str] = []
    for line in (answer or "").split("\n"):
        stripped = line.strip()
        if not stripped or _HEADING.match(line) or stripped.startswith("|---"):
            kept_lines.append(line)
            continue
        if stripped.startswith("|"):
            if _normalize(stripped.strip("|")) in failing_claims or _normalize(stripped) in failing_claims:
                removed.append(stripped)
                continue
            kept_lines.append(line)
            continue
        bullet = _BULLET.match(line)
        prefix = bullet.group(1) if bullet else ""
        body = line[len(prefix):] if prefix else line
        segments = _split_keep(body)
        kept = [s for s in segments if _normalize(s) not in failing_claims]
        removed.extend(s for s in segments if _normalize(s) in failing_claims)
        if kept:
            kept_lines.append(prefix + " ".join(s.strip() for s in kept))

    body = "\n".join(_drop_orphan_headings(kept_lines)).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    if allowed_evidence_ids is not None:
        body = remove_invalid_markers(body, allowed_evidence_ids)

    notes: List[str] = []
    unsafe_claims = {_normalize(f["claim"]) for f in failures if f.get("status") == "unsafe_procedure" and f.get("claim")}
    for f in failures:
        if f.get("status") != "unsafe_procedure" and _normalize(f.get("claim") or "") in unsafe_claims:
            continue  # the unsafe-procedure note already covers this removed claim
        template = _USER_MESSAGES.get(f.get("status"), "A technical detail could not be confirmed and was removed.")
        message = template.format(id=f.get("identifier") or "this item")
        if message not in notes:
            notes.append(message)

    remaining_material = [
        s for s in re.split(r"(?<=[.!?])\s+", MARKER_PATTERN.sub("", body))
        if len(s.strip()) >= 25 and not s.strip().endswith("?")
    ]
    sections: List[str] = [
        body if remaining_material else
        "I could not confirm a verified procedure for this from the available SAP documentation."
    ]
    sections.append(UNRESOLVED_HEADING + "\n" + "\n".join(f"- {n}" for n in notes))
    if evidence_needed:
        sections.append("Could you confirm the following so the correct procedure can be identified?\n" + "\n".join(f"- {e}" for e in evidence_needed))
    if clarification_question and clarification_question.lower()[:40] not in body.lower():
        sections.append(clarification_question)

    return {"answer": "\n\n".join(sections).strip(), "applied": True, "removed_claims": removed}
