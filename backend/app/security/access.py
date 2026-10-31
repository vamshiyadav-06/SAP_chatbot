"""Document-level access control for retrieval (AUDIT_REPORT F-01)."""

from typing import Any, FrozenSet, Iterable, List, Optional

from backend.app.config import settings


def retrieval_groups(user: Any) -> Optional[FrozenSet[str]]:
    """The access groups whose documents `user` may retrieve; None means unrestricted (admins).
    Calls without a user (offline evaluation scripts) get only the default group."""
    if user is not None and getattr(user, "is_admin", False):
        return None
    groups = (getattr(user, "groups", None) if user is not None else None) or [settings.DEFAULT_ACCESS_GROUP]
    return frozenset(g.strip() for g in groups if isinstance(g, str) and g.strip())


def document_visible(document_groups: Optional[Iterable[str]], allowed: Optional[FrozenSet[str]]) -> bool:
    if allowed is None:
        return True
    return bool(allowed.intersection(document_groups or ()))


def normalize_groups(groups: Iterable[str]) -> List[str]:
    """Trimmed, de-duplicated, non-empty group names (order kept)."""
    seen: List[str] = []
    for group in groups or []:
        name = str(group).strip()
        if name and name not in seen:
            seen.append(name)
    return seen
