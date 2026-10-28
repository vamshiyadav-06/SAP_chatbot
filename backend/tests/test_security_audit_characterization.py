"""Regression tests for security audit findings; no live DB or external services."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from datetime import timedelta

from backend.app.main import app
from backend.app.database import get_db
from backend.app.api import auth as auth_api, chats as chats_api, rag as rag_api
from backend.app.security.auth import get_current_user, create_access_token
from backend.app.models.user import User
from backend.app.schemas.auth import UserRegister


@pytest.fixture
def audit_client(monkeypatch):
    db = MagicMock()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def regular(**updates):
    fields = dict(id="user-1", email="u@example.com", name="User", is_admin=False,
                  role="consultant", token_version=0, created_at=datetime.now(timezone.utc))
    fields.update(updates)
    return SimpleNamespace(**fields)


def test_public_registration_is_always_regular_and_ignores_role(audit_client, monkeypatch):
    client, db = audit_client
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(auth_api, "hash_password", lambda _: "hash")
    created = []
    db.add.side_effect = created.append
    def refresh(user):
        user.id = "created"
        user.created_at = datetime.now(timezone.utc)
    db.refresh.side_effect = refresh
    response = client.post("/api/auth/register", json={
        "email": "new@example.com", "name": "New User", "password": "Long-Secure-Password-123", "role": "admin"
    })
    assert response.status_code == 201
    assert created[0].is_admin is False
    assert created[0].role == "consultant"


def test_demo_login_removed(audit_client):
    client, db = audit_client
    assert client.post("/api/auth/demo").status_code == 404
    db.query.assert_not_called()


def test_document_extraction_requires_authentication(audit_client, monkeypatch):
    client, _ = audit_client
    extract = MagicMock()
    monkeypatch.setattr(chats_api, "extract_document", extract)
    response = client.post("/api/chats/extract-document", files={"file": ("x.txt", b"contents", "text/plain")})
    assert response.status_code == 401
    extract.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
def test_regular_rag_response_strips_internal_evidence_metadata(audit_client, monkeypatch, stream):
    client, _ = audit_client
    app.dependency_overrides[get_current_user] = lambda: regular()
    result = dict(answer="Answer [E1]", source_type="knowledge_base", grounding_score=0.9,
                  citations=[{"document": "SECRET_DOC", "snippet": "SECRET_EVIDENCE"}], web_sources=[], images=[],
                  source_scores={"secret": .9}, comparison_audit={"secret": "SECRET_COMPARE"},
                  internal_evidence_confidence=.99, selected_evidence_quality=.9, kb_score=.9)
    monkeypatch.setattr(rag_api.rag_service, "process_query", lambda *a, **k: result.copy())
    monkeypatch.setattr(rag_api.rag_service, "stream_query", lambda *a, **k: iter([dict(type="done", **result)]))
    response = client.post("/api/rag/query/stream" if stream else "/api/rag/query", json={"query": "question"})
    assert response.status_code == 200
    for secret in ("SECRET_DOC", "SECRET_EVIDENCE", "SECRET_COMPARE", "source_scores", "[E1]"):
        assert secret not in response.text


def test_registration_rejects_weak_password_and_ignores_role():
    with pytest.raises(ValueError):
        UserRegister(email="u@example.com", name="User", password="abcdef", role="admin")


def test_registration_rejects_password_over_bcrypt_utf8_byte_limit():
    with pytest.raises(ValueError):
        UserRegister(email="u@example.com", name="User", password="é" * 37)


def test_revoked_access_token_is_rejected():
    db = MagicMock()
    user = regular(token_version=2)
    db.query.return_value.filter.return_value.first.return_value = user
    token = create_access_token({"sub": user.id, "ver": 1}, expires_delta=timedelta(minutes=1))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        get_current_user(token=token, db=db)
    assert error.value.status_code == 401


def test_admin_seed_does_not_promote_existing_email(monkeypatch):
    from backend.app import database
    from backend.app.config import settings
    existing = regular(password_hash="kept")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    factory = MagicMock()
    factory.return_value.__enter__.return_value = db
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(settings, "SUPER_ADMIN_EMAIL", existing.email)
    database.seed_super_admin()
    assert existing.is_admin is False
    db.commit.assert_not_called()
