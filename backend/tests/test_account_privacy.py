"""F-31 account data export/deletion and attachment-retention regressions."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fastapi.testclient import TestClient
from fastapi import HTTPException

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.audit_event import AuditEvent
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.shared_prompt import SharedPrompt
from backend.app.models.uploaded_attachment import UploadedAttachment
from backend.app.models.user import User
from backend.app.api.auth import delete_my_account
from backend.scripts.purge_expired_attachments import purge_expired_attachments
from backend.app.security.auth import create_access_token, hash_password


def _account_graph():
    suffix = uuid.uuid4().hex
    db = SessionLocal()
    user = User(
        email=f"privacy-{suffix}@example.com", name="Privacy Test", password_hash=hash_password("long-test-password"),
        is_admin=False, role="consultant",
    )
    db.add(user)
    db.flush()
    chat = Chat(user_id=user.id, title="Private test chat", summary="Summary of private question")
    db.add(chat)
    db.flush()
    message = Message(chat_id=chat.id, role="user", content="My private question")
    db.add(message)
    db.flush()
    attachment = UploadedAttachment(
        message_id=message.id, name="notes.txt", file_type="txt", page_count=1,
        extracted_text="Private extracted attachment text",
    )
    shared = SharedPrompt(
        message_id=message.id, token=uuid.uuid4().hex, content="My private question", answer="A shared answer",
    )
    db.add_all([attachment, shared])
    db.commit()
    ids = {"user": user.id, "chat": chat.id, "message": message.id, "attachment": attachment.id,
           "shared": shared.id, "email": user.email, "share_token": shared.token}
    token = create_access_token(data={"sub": user.id, "ver": user.token_version})
    db.close()
    return ids, {"Authorization": f"Bearer {token}"}


def test_account_export_contains_owned_chat_and_attachment_data_without_credentials():
    ids, headers = _account_graph()
    try:
        with TestClient(app) as client:
            response = client.get("/api/auth/me/export", headers=headers)
        assert response.status_code == 200, response.text
        assert "attachment; filename=\"account-export-" in response.headers["content-disposition"]
        payload = response.json()
        assert payload["account"]["email"] == ids["email"]
        message = payload["chats"][0]["messages"][0]
        assert message["content"] == "My private question"
        assert message["attachments"][0]["extracted_text"] == "Private extracted attachment text"
        assert message["shared_link"]["content"] == "My private question"
        serialized = response.text
        assert "password_hash" not in serialized
        assert "share_token" not in serialized
        assert ids["share_token"] not in serialized
        assert "embedding" not in serialized
    finally:
        with SessionLocal() as db:
            user = db.get(User, ids["user"])
            if user:
                db.delete(user)
                db.commit()


def test_account_deletion_cascades_private_content_and_invalidates_token():
    ids, headers = _account_graph()
    with TestClient(app) as client:
        response = client.delete("/api/auth/me", headers=headers)
        assert response.status_code == 204
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    with SessionLocal() as db:
        assert db.get(User, ids["user"]) is None
        assert db.get(Chat, ids["chat"]) is None
        assert db.get(Message, ids["message"]) is None
        assert db.get(UploadedAttachment, ids["attachment"]) is None
        assert db.get(SharedPrompt, ids["shared"]) is None
        assert db.query(AuditEvent).filter(
            AuditEvent.action == "account_delete", AuditEvent.actor_id == ids["user"]
        ).count() == 1


def test_final_administrator_cannot_delete_themselves():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    admin = SimpleNamespace(id="last-admin", email="admin@example.com", is_admin=True)
    with pytest.raises(HTTPException) as exc_info:
        delete_my_account(SimpleNamespace(headers={}), admin, db)
    assert getattr(exc_info.value, "status_code", None) == 409
    db.delete.assert_not_called()


def test_attachment_retention_is_dry_run_by_default_and_uses_parent_message_time():
    suffix = uuid.uuid4().hex
    db = SessionLocal()
    user = User(email=f"retention-{suffix}@example.com", name="Retention Test", password_hash="not-a-login")
    db.add(user)
    db.flush()
    chat = Chat(user_id=user.id, title="Retention test")
    db.add(chat)
    db.flush()
    now = datetime.now(timezone.utc)
    expired_message = Message(chat_id=chat.id, role="user", content="old", created_at=now - timedelta(days=400))
    recent_message = Message(chat_id=chat.id, role="user", content="recent", created_at=now - timedelta(days=5))
    db.add_all([expired_message, recent_message])
    db.flush()
    expired = UploadedAttachment(message_id=expired_message.id, name="old.txt", file_type="txt", extracted_text="old")
    recent = UploadedAttachment(message_id=recent_message.id, name="new.txt", file_type="txt", extracted_text="new")
    db.add_all([expired, recent])
    db.commit()
    expired_id, recent_id, user_id = expired.id, recent.id, user.id
    try:
        assert purge_expired_attachments(db, retention_days=0, now=now, apply=True) == 0
        assert purge_expired_attachments(db, retention_days=365, now=now, apply=False) == 1
        assert db.get(UploadedAttachment, expired_id) is not None
        assert purge_expired_attachments(db, retention_days=365, now=now, apply=True) == 1
        assert db.get(UploadedAttachment, expired_id) is None
        assert db.get(UploadedAttachment, recent_id) is not None
    finally:
        owner = db.get(User, user_id)
        if owner:
            db.delete(owner)
            db.commit()
        db.close()
