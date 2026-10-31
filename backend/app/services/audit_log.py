"""
Writes security audit events (AUDIT_REPORT F-25).

Each event is written in its own short session, so recording never joins (or rolls back with) the
request's transaction, and a failure to record is logged instead of breaking the request.
Never pass passwords, tokens, prompts or answers in `details`.
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.app.database import SessionLocal
from backend.app.models.audit_event import AuditEvent
from backend.app.security.ratelimit import client_ip

logger = logging.getLogger(__name__)


def actor_of(principal: Any):
    """(actor_id, actor_type) for a user object, the admin-key marker, or None."""
    if principal == "admin_key" or principal is True:
        return None, "admin_key"
    if principal is None:
        return None, "anonymous"
    return getattr(principal, "id", None), "admin" if getattr(principal, "is_admin", False) else "user"


def record(
    action: str,
    outcome: str = "success",
    *,
    request: Any = None,
    principal: Any = None,
    actor_id: Optional[str] = None,
    actor_type: Optional[str] = None,
    target: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    if actor_type is None:
        actor_id, actor_type = actor_of(principal)
    event = AuditEvent(
        action=action[:64],
        outcome=outcome[:20],
        actor_id=actor_id,
        actor_type=actor_type,
        target=(str(target)[:255] if target is not None else None),
        ip=(client_ip(request)[:64] if request is not None else None),
        user_agent=((request.headers.get("user-agent") or "")[:300] if request is not None else None),
        details=(json.dumps(details, default=str)[:4000] if details else None),
    )
    try:
        with SessionLocal() as db:
            db.add(event)
            db.commit()
    except Exception as exc:
        logger.error("Could not record audit event %s: %s", action, type(exc).__name__)
