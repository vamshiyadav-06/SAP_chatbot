"""Dry-run or purge attachments older than their parent message's retention cutoff."""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def purge_expired_attachments(db, *, retention_days: int, now=None, apply: bool = False) -> int:
    """Count expired attachment rows; delete only when explicitly requested."""
    from backend.app.models.message import Message
    from backend.app.models.uploaded_attachment import UploadedAttachment

    if retention_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=retention_days)
    expired_message_ids = select(Message.id).where(Message.created_at < cutoff)
    query = db.query(UploadedAttachment).filter(UploadedAttachment.message_id.in_(expired_message_ids))
    count = query.count()
    if apply and count:
        query.delete(synchronize_session=False)
        db.commit()
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete expired attachment rows; default is dry-run")
    args = parser.parse_args()
    from backend.app.config import settings
    from backend.app.database import SessionLocal
    from backend.app.services import audit_log

    with SessionLocal() as db:
        count = purge_expired_attachments(
            db, retention_days=settings.ATTACHMENT_RETENTION_DAYS, apply=args.apply
        )
    mode = "deleted" if args.apply else "would delete"
    print(f"{count} attachment(s) {mode} at a {settings.ATTACHMENT_RETENTION_DAYS}-day retention.")
    if args.apply and count:
        audit_log.record(
            "attachment_retention_purge", actor_type="system", actor_id=None,
            details={"deleted_count": count, "retention_days": settings.ATTACHMENT_RETENTION_DAYS},
        )


if __name__ == "__main__":
    main()
