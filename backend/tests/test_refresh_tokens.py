"""Refresh tokens: an HttpOnly cookie, rotated on every use, stored only as a SHA-256 hash, with reuse
detection (a rotated token presented after the grace window revokes its whole family). Also covers the
account export filtering and the concurrent duplicate registration fixed in the same change.
Runs against the *_test database (conftest.py)."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.chat import Chat
from backend.app.models.citation import Citation
from backend.app.models.message import Message
from backend.app.models.organization import Organization
from backend.app.models.refresh_token import RefreshToken
from backend.app.models.user import User
from backend.app.models.web_image import WebImage
from backend.app.models.web_source import WebSource
from backend.tests.org_helpers import PASSWORD, OrgFixtures, headers_for, random_password

REFRESH = "/api/auth/refresh"
CSRF = {"X-Refresh-Request": "1"}
COOKIE = settings.REFRESH_COOKIE_NAME


@pytest.fixture
def fx():
    fixtures = OrgFixtures()
    yield fixtures
    fixtures.cleanup()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _refresh_cookie_header(response):
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{COOKIE}="):
            return header
    return None


def _cookie_value(header: str) -> str:
    return header.split(";", 1)[0].split("=", 1)[1].strip('"')


def _attributes(header: str) -> dict:
    attributes = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        attributes[name.lower()] = value or True
    return attributes


def _is_cleared(response) -> bool:
    header = _refresh_cookie_header(response)
    if header is None:
        return False
    attributes = _attributes(header)
    return _cookie_value(header) == "" or attributes.get("max-age") == "0"


def _row(raw: str):
    with SessionLocal() as db:
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash(raw)).one_or_none()
        if row is not None:
            db.expunge(row)
        return row


def _update_row(raw: str, **values):
    with SessionLocal() as db:
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == _hash(raw)).one()
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()


def _set_user(user_id: str, **values):
    with SessionLocal() as db:
        user = db.get(User, user_id)
        for key, value in values.items():
            setattr(user, key, value)
        db.commit()


def _sign_in(client: TestClient, user: User, path: str = "/api/auth/login"):
    response = client.post(path, json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    header = _refresh_cookie_header(response)
    assert header is not None, "sign-in must set the refresh cookie"
    return response, _cookie_value(header)


def _refresh_with(raw: str, *, csrf=True):
    """A client that holds only the given refresh cookie (as a browser tab would)."""
    headers = {"Cookie": f"{COOKIE}={raw}"}
    if csrf:
        headers.update(CSRF)
    return TestClient(app).post(REFRESH, headers=headers)


# ---------------------------------------------------------------------------- issuing the cookie

@pytest.mark.parametrize("kind", ["individual", "admin", "organisation"])
def test_every_sign_in_sets_a_locked_down_refresh_cookie(fx, kind):
    if kind == "organisation":
        user, path = fx.user(org=fx.organisation(), role="member"), "/api/org/auth/login"
    elif kind == "admin":
        user, path = fx.user(is_admin=True), "/api/auth/admin-login"
    else:
        user, path = fx.user(), "/api/auth/login"
    client = TestClient(app)

    response, raw = _sign_in(client, user, path)

    body = response.json()
    assert set(body) == {"access_token", "token_type", "user"}, "the JSON shape stays as before"
    assert body["token_type"] == "bearer" and body["user"]["id"] == user.id
    attributes = _attributes(_refresh_cookie_header(response))
    assert attributes.get("httponly") is True
    assert str(attributes.get("samesite")).lower() == "strict"
    assert attributes.get("path") == "/api/auth"
    assert attributes.get("max-age") == str(settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)
    assert "secure" not in attributes, "Secure only in production (plain-HTTP development would drop it)"
    assert len(raw) >= 43, "256 bits of randomness"

    row = _row(raw)
    assert row is not None and row.user_id == user.id
    assert row.token_hash == _hash(raw) and raw not in row.token_hash, "only the hash is stored"
    assert row.token_version == 0 and row.rotated_at is None and row.revoked_at is None
    assert timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS - 1) < row.expires_at - _now() <= timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def test_refresh_cookie_is_secure_in_production(fx):
    user = fx.user()
    client = TestClient(app, base_url="https://testserver")
    with patch.object(settings, "ENVIRONMENT", "production"):
        response = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert _attributes(_refresh_cookie_header(response)).get("secure") is True


def test_each_sign_in_starts_a_new_family(fx):
    user = fx.user()
    _, first = _sign_in(TestClient(app), user)
    _, second = _sign_in(TestClient(app), user)
    assert _row(first).family_id != _row(second).family_id


# ---------------------------------------------------------------------------- refreshing

def test_refresh_rotates_the_cookie_and_returns_a_working_access_token(fx):
    user = fx.user()
    client = TestClient(app)
    _, first = _sign_in(client, user)

    response = client.post(REFRESH, headers=CSRF)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"access_token", "token_type", "user"}
    assert body["user"]["id"] == user.id
    second = _cookie_value(_refresh_cookie_header(response))
    assert second and second != first
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["id"] == user.id

    old, new = _row(first), _row(second)
    assert old.rotated_at is not None and old.replaced_by_id == new.id
    assert new.family_id == old.family_id and new.rotated_at is None and new.revoked_at is None
    assert new.expires_at == old.expires_at, "rotation never extends the session beyond its first sign-in"

    again = client.post(REFRESH, headers=CSRF)  # the jar now holds the new cookie
    assert again.status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-Refresh-Request": "0"}, {"X-Requested-With": "XMLHttpRequest"}])
def test_refresh_without_the_csrf_header_is_forbidden(fx, headers):
    user = fx.user()
    client = TestClient(app)
    _, raw = _sign_in(client, user)

    response = client.post(REFRESH, headers=headers)

    assert response.status_code == 403
    assert _row(raw).rotated_at is None, "nothing is rotated"


def test_refresh_reads_only_the_cookie(fx):
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)
    fresh = TestClient(app)
    for response in (
        fresh.post(REFRESH, headers=CSRF, json={"refresh_token": raw}),
        fresh.post(f"{REFRESH}?refresh_token={raw}", headers=CSRF),
        fresh.post(REFRESH, headers={**CSRF, "Authorization": f"Bearer {raw}"}),
    ):
        assert response.status_code == 401
    assert _row(raw).rotated_at is None


@pytest.mark.parametrize("cookie", [None, "", "not-a-real-token", "x" * 43])
def test_missing_or_unknown_cookie_is_401_and_clears_the_cookie(cookie):
    headers = dict(CSRF)
    if cookie is not None:
        headers["Cookie"] = f"{COOKIE}={cookie}"

    response = TestClient(app).post(REFRESH, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Your session has ended. Please sign in again."
    assert _is_cleared(response)


def test_expired_refresh_token_is_rejected(fx):
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)
    _update_row(raw, expires_at=_now() - timedelta(seconds=1))

    response = _refresh_with(raw)

    assert response.status_code == 401 and _is_cleared(response)


def test_reuse_within_the_grace_window_is_allowed(fx):
    """Two tabs refreshing at once both present the same cookie; neither may be signed out."""
    user = fx.user()
    client = TestClient(app)
    _, first = _sign_in(client, user)
    assert client.post(REFRESH, headers=CSRF).status_code == 200  # tab A rotates first -> second

    late = _refresh_with(first)  # tab B still sent the first cookie

    assert late.status_code == 200, late.text
    sibling = _cookie_value(_refresh_cookie_header(late))
    assert _row(sibling).family_id == _row(first).family_id and _row(sibling).revoked_at is None
    assert client.post(REFRESH, headers=CSRF).status_code == 200, "tab A's token still works"


def test_reuse_after_the_grace_window_revokes_the_whole_family(fx):
    user = fx.user()
    client = TestClient(app)
    _, first = _sign_in(client, user)
    rotated = client.post(REFRESH, headers=CSRF)
    second = _cookie_value(_refresh_cookie_header(rotated))
    _update_row(first, rotated_at=_now() - timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS + 5))

    stolen = _refresh_with(first)

    assert stolen.status_code == 401 and _is_cleared(stolen)
    family = _row(first).family_id
    with SessionLocal() as db:
        rows = db.query(RefreshToken).filter(RefreshToken.family_id == family).all()
        assert rows and all(row.revoked_at is not None for row in rows)
    assert client.post(REFRESH, headers=CSRF).status_code == 401, "the legitimate holder must sign in again"
    assert _row(second).revoked_at is not None


def test_other_sessions_survive_a_revoked_family(fx):
    user = fx.user()
    _, laptop = _sign_in(TestClient(app), user)
    phone_client = TestClient(app)
    _, phone = _sign_in(phone_client, user)
    _refresh_with(laptop)
    _update_row(laptop, rotated_at=_now() - timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS + 5))
    assert _refresh_with(laptop).status_code == 401

    assert phone_client.post(REFRESH, headers=CSRF).status_code == 200


# ---------------------------------------------------------------------------- revocation through account state

def test_password_change_ends_older_refresh_tokens_and_issues_a_new_one(fx):
    user = fx.user()
    client = TestClient(app)
    signed_in, old = _sign_in(client, user)
    headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}

    changed = client.post("/api/auth/change-password", headers=headers,
                          json={"current_password": PASSWORD, "new_password": random_password()})

    assert changed.status_code == 200, changed.text
    new = _cookie_value(_refresh_cookie_header(changed))
    assert new != old
    assert _refresh_with(old).status_code == 401
    assert _refresh_with(new).status_code == 200


def test_forced_password_change_of_an_organisation_member_issues_a_session_cookie(fx):
    member = fx.user(org=fx.organisation(), role="member", must_change_password=True)
    client = TestClient(app)
    signed_in, first = _sign_in(client, member, "/api/org/auth/login")
    assert signed_in.json()["user"]["must_change_password"] is True
    assert _refresh_with(first).status_code == 200, "a pending password change still refreshes, like sign-in"

    changed = client.post("/api/auth/change-password", headers=headers_for(member.id),
                          json={"current_password": PASSWORD, "new_password": random_password()})

    assert changed.status_code == 200, changed.text
    refreshed = _refresh_with(_cookie_value(_refresh_cookie_header(changed)))
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["must_change_password"] is False


def test_token_version_change_rejects_the_refresh_token(fx):
    """Admin/org-admin password resets, deactivation and org status changes all bump token_version."""
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)
    with SessionLocal() as db:
        db.get(User, user.id).token_version += 1
        db.commit()

    assert _refresh_with(raw).status_code == 401


def test_logout_revokes_refresh_tokens_and_clears_the_cookie(fx):
    user = fx.user()
    client = TestClient(app)
    signed_in, raw = _sign_in(client, user)
    _, other_device = _sign_in(TestClient(app), user)

    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {signed_in.json()['access_token']}"})

    assert response.status_code == 204
    assert _is_cleared(response)
    assert _attributes(_refresh_cookie_header(response)).get("path") == "/api/auth"
    assert _refresh_with(raw).status_code == 401
    assert _refresh_with(other_device).status_code == 401, "logout ends every session of the account"
    assert _row(raw).revoked_at is not None


def test_logout_with_an_expired_access_token_still_ends_the_cookie_session(fx):
    """The browser may log out after its 15-minute access token expired; the cookie must not survive."""
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)

    response = TestClient(app).post("/api/auth/logout", headers={"Cookie": f"{COOKIE}={raw}",
                                                                 "Authorization": "Bearer expired.or.invalid"})

    assert response.status_code == 204
    assert _is_cleared(response)
    assert _refresh_with(raw).status_code == 401


def test_logout_without_any_credential_is_401():
    assert TestClient(app).post("/api/auth/logout").status_code == 401


def test_inactive_user_cannot_refresh(fx):
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)
    _set_user(user.id, is_active=False)  # without a token_version bump

    assert _refresh_with(raw).status_code == 401


def test_organisation_member_refresh_works_until_the_organisation_is_suspended(fx):
    org = fx.organisation()
    member = fx.user(org=org, role="member")
    client = TestClient(app)
    _sign_in(client, member, "/api/org/auth/login")

    refreshed = client.post(REFRESH, headers=CSRF)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["user"]["account_type"] == "organisation"
    assert refreshed.json()["user"]["organization_id"] == org.id

    with SessionLocal() as db:
        db.get(Organization, org.id).status = "suspended"  # without a token_version bump
        db.commit()
    assert client.post(REFRESH, headers=CSRF).status_code == 401


def test_deleting_the_user_removes_their_refresh_tokens(fx):
    user = fx.user()
    _, raw = _sign_in(TestClient(app), user)
    with SessionLocal() as db:
        db.delete(db.get(User, user.id))
        db.commit()
    assert _row(raw) is None


# ---------------------------------------------------------------------------- account export and registration

def _answer_with_sources(user_id: str) -> str:
    with SessionLocal() as db:
        chat = Chat(user_id=user_id, title="Export test")
        db.add(chat)
        db.flush()
        answer = Message(chat_id=chat.id, role="assistant", content="Use the charge plan [E1] in SAP CC [E2].")
        db.add(answer)
        db.flush()
        db.add_all([
            Citation(message_id=answer.id, document_id="doc-internal.pdf", document_name="internal-runbook.pdf",
                     chunk_id=str(uuid.uuid4()), page_number=7, section="Rating",
                     similarity_score=0.9, citation_text="Confidential knowledge-base excerpt"),
            WebSource(message_id=answer.id, url="https://example.com/sap-cc", title="Example web source",
                      domain="example.com", snippet="Web snippet text"),
            WebImage(message_id=answer.id, url="https://example.com/diagram.png", description="Diagram",
                     alt_text="Rating flow", source_url="https://example.com/source-page",
                     source_title="Image source title"),
        ])
        db.commit()
        return answer.id


def test_account_export_hides_sources_and_markers_from_regular_users(fx):
    user = fx.user()
    _answer_with_sources(user.id)

    response = TestClient(app).get("/api/auth/me/export", headers=headers_for(user.id))

    assert response.status_code == 200, response.text
    message = response.json()["chats"][0]["messages"][0]
    assert message["citations"] == [] and message["web_sources"] == []
    assert "[E1]" not in message["content"] and "[E2]" not in message["content"]
    assert message["content"].startswith("Use the charge plan")
    assert message["images"][0]["url"] == "https://example.com/diagram.png"
    assert message["images"][0]["source_url"] is None and message["images"][0]["source_title"] is None
    for leaked in ("Confidential knowledge-base excerpt", "internal-runbook.pdf", "Web snippet text",
                   "https://example.com/sap-cc", "https://example.com/source-page"):
        assert leaked not in response.text


def test_account_export_keeps_sources_for_administrators(fx):
    admin = fx.user(is_admin=True)
    _answer_with_sources(admin.id)

    response = TestClient(app).get("/api/auth/me/export", headers=headers_for(admin.id))

    message = response.json()["chats"][0]["messages"][0]
    assert message["citations"][0]["citation_text"] == "Confidential knowledge-base excerpt"
    assert message["web_sources"][0]["url"] == "https://example.com/sap-cc"
    assert "[E1]" in message["content"]


def test_concurrent_duplicate_registration_gets_the_normal_400(fx, monkeypatch):
    """Two sign-ups racing for one e-mail: both pass the lookup, the second commit hits the unique index."""
    existing = fx.user()
    from backend.app.api import auth as auth_api
    monkeypatch.setattr(auth_api, "_email_registered", lambda db, email: False)

    response = TestClient(app).post("/api/auth/register", json={
        "email": existing.email, "name": "Racing Person", "password": "abcd1234"})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Registration could not be completed."
