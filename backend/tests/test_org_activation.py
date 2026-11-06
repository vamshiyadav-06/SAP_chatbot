"""Organisation activation codes, organisation requests and migration 0006 (docs/ORGANISATION_PORTAL.md).

Runs against the *_test database (conftest.py)."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from backend.app.config import settings
from backend.app.database import SessionLocal, engine, run_migrations, schema_revision_status
from backend.app.main import app
from backend.app.models.audit_event import AuditEvent
from backend.app.models.organization import OrgActivationCode, Organization
from backend.app.models.user import User
from backend.app.services.org_credentials import hash_activation_code, normalise_activation_code
from backend.tests.org_helpers import OrgFixtures, headers_for, random_password, unique

client = TestClient(app)
GENERIC = "This activation code is not valid. Ask your Clyptus administrator for a new code."


@pytest.fixture
def fx():
    fixtures = OrgFixtures()
    yield fixtures
    fixtures.cleanup()


@pytest.fixture
def super_admin(fx):
    admin = fx.user(is_admin=True)
    return admin, headers_for(admin.id)


def _create_org(fx, admin_headers, **overrides):
    body = {"name": unique("Acme Org"), "contact_email": "Ops@Example.com",
            "admin_name": "Ada Admin", "admin_email": f"{unique('owner')}@Example.com"}
    body.update(overrides)
    response = client.post("/api/admin/organisations", json=body, headers=admin_headers)
    assert response.status_code == 201, response.text
    data = response.json()
    fx.track_org(data["organisation"]["id"])
    return body, data


def test_migration_0006_is_applied_and_idempotent():
    run_migrations()
    run_migrations()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"organizations", "org_activation_codes", "org_shared_answers", "org_answer_likes",
            "org_answer_comments"} <= tables
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"account_type", "organization_id", "org_role", "is_active", "must_change_password",
            "last_login_at"} <= user_columns
    with engine.connect() as conn:
        # 0006 and every later migration are applied.
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == schema_revision_status()[1]
        assert conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_organization_id'")).first() is not None
        # Existing accounts became active individual accounts.
        assert conn.execute(text(
            "SELECT count(*) FROM users WHERE account_type IS NULL OR is_active IS NULL")).scalar() == 0


def test_super_admin_creates_organisation_and_owner_activates_it(fx, super_admin, caplog):
    caplog.set_level(logging.DEBUG)
    _, admin_headers = super_admin
    body, created = _create_org(fx, admin_headers)
    code = created["activation_code"]
    assert normalise_activation_code(code) == code
    organisation = created["organisation"]
    assert organisation["status"] == "pending_activation"
    assert organisation["active_code"]["hint"] == code[-4:]
    assert organisation["active_code"]["admin_email"] == body["admin_email"].lower()

    # Only the hash and the hint are stored.
    with SessionLocal() as db:
        row = db.query(OrgActivationCode).filter(OrgActivationCode.organization_id == organisation["id"]).one()
        assert row.code_hash == hash_activation_code(code)
        assert code not in (row.code_hash, row.code_hint)

    verify = client.post("/api/org/activation/verify", json={"code": code.lower().replace("-", " ")})
    assert verify.status_code == 200, verify.text
    assert verify.json()["organisation_name"] == body["name"]
    assert verify.json()["admin_email"] == body["admin_email"].lower()
    assert verify.json()["admin_name"] == "Ada Admin"
    assert verify.json()["expires_at"].endswith("+00:00")

    password = random_password()
    complete = client.post("/api/org/activation/complete", json={"code": code, "name": "Ada Owner", "password": password})
    assert complete.status_code == 201, complete.text
    # Activation signs the owner in: the same HttpOnly refresh cookie as every other sign-in.
    refresh_cookie = next(h for h in complete.headers.get_list("set-cookie")
                          if h.startswith(f"{settings.REFRESH_COOKIE_NAME}="))
    assert "HttpOnly" in refresh_cookie and "Path=/api/auth" in refresh_cookie
    token = complete.json()
    user = token["user"]
    fx.track_user(user["id"])
    assert user["account_type"] == "organisation"
    assert user["org_role"] == "owner"
    assert user["organization_name"] == body["name"]
    assert user["must_change_password"] is False
    me = client.get("/api/org/me", headers={"Authorization": f"Bearer {token['access_token']}"})
    assert me.status_code == 200
    assert me.json()["organisation"]["status"] == "active"
    assert me.json()["role"] == "owner" and me.json()["can_manage"] is True

    # Single use: the same code cannot be used again, with the same generic message.
    again = client.post("/api/org/activation/complete", json={"code": code, "name": "Mallory", "password": password})
    assert again.status_code == 400 and again.json()["detail"] == GENERIC
    assert client.post("/api/org/activation/verify", json={"code": code}).json()["detail"] == GENERIC

    # The owner signs in through the organisation portal only.
    assert client.post("/api/org/auth/login", json={"email": user["email"], "password": password}).status_code == 200
    individual = client.post("/api/auth/login", json={"email": user["email"], "password": password})
    assert individual.status_code == 403
    assert individual.json()["detail"] == "This is an organisation account. Sign in through the Organisation Portal."

    # The plaintext code never reaches the audit log or the application log.
    with SessionLocal() as db:
        events = db.query(AuditEvent).filter(AuditEvent.target == organisation["id"]).all()
        actions = {event.action for event in events}
        assert {"org_create", "org_activation_code_issue", "org_activation"} <= actions
        dumped = " ".join(f"{e.target} {e.details}" for e in db.query(AuditEvent).order_by(
            AuditEvent.created_at.desc()).limit(200).all())
    body_part = code[4:].replace("-", "")
    assert code not in dumped and body_part not in dumped
    assert code not in caplog.text and body_part not in caplog.text and password not in caplog.text


@pytest.mark.parametrize("change", ["expired", "revoked", "unknown", "malformed"])
def test_unusable_codes_fail_with_one_generic_message(fx, super_admin, change):
    _, admin_headers = super_admin
    _, created = _create_org(fx, admin_headers)
    code = created["activation_code"]
    with SessionLocal() as db:
        row = db.query(OrgActivationCode).filter(OrgActivationCode.code_hash == hash_activation_code(code)).one()
        if change == "expired":
            row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        if change == "revoked":
            row.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    if change == "unknown":
        code = "CLY-AAAA-BBBB-CCCC-DDDD"
    if change == "malformed":
        code = "not a code"
    verify = client.post("/api/org/activation/verify", json={"code": code})
    complete = client.post("/api/org/activation/complete",
                           json={"code": code, "name": "Someone", "password": random_password()})
    assert (verify.status_code, verify.json()) == (400, {"detail": GENERIC})
    assert (complete.status_code, complete.json()) == (400, {"detail": GENERIC})
    with SessionLocal() as db:
        assert db.get(Organization, created["organisation"]["id"]).status == "pending_activation"


def test_reissue_revokes_previous_code(fx, super_admin):
    _, admin_headers = super_admin
    _, created = _create_org(fx, admin_headers)
    org_id = created["organisation"]["id"]
    first = created["activation_code"]
    reissued = client.post(f"/api/admin/organisations/{org_id}/activation-codes", headers=admin_headers)
    assert reissued.status_code == 200, reissued.text
    second = reissued.json()["activation_code"]
    assert second != first
    assert client.post("/api/org/activation/verify", json={"code": first}).status_code == 400
    assert client.post("/api/org/activation/verify", json={"code": second}).status_code == 200


def test_concurrent_completion_creates_exactly_one_owner(fx, super_admin):
    _, admin_headers = super_admin
    _, created = _create_org(fx, admin_headers)
    code = created["activation_code"]

    def attempt(index):
        return TestClient(app).post("/api/org/activation/complete",
                                    json={"code": code, "name": f"Racer {index}", "password": random_password()})

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(attempt, range(3)))
    statuses = sorted(result.status_code for result in results)
    assert statuses == [201, 400, 400]
    with SessionLocal() as db:
        owners = db.query(User).filter(User.organization_id == created["organisation"]["id"]).all()
        assert len(owners) == 1 and owners[0].org_role == "owner"


def test_activation_endpoints_are_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "ORG_ACTIVATION_RATE_LIMIT_PER_MINUTE", 2)
    codes = [client.post("/api/org/activation/verify", json={"code": "CLY-AAAA-BBBB-CCCC-DDDD"}).status_code
             for _ in range(3)]
    assert codes == [400, 400, 429]


def test_activation_password_rules_apply(fx, super_admin):
    _, admin_headers = super_admin
    _, created = _create_org(fx, admin_headers)
    short = client.post("/api/org/activation/complete",
                        json={"code": created["activation_code"], "name": "Owner", "password": "short"})
    assert short.status_code == 422


def test_admin_email_already_registered_is_rejected_at_issue(fx, super_admin):
    _, admin_headers = super_admin
    existing = fx.user()
    response = client.post("/api/admin/organisations", headers=admin_headers, json={
        "name": unique("Taken Email Org"), "contact_email": "c@example.com", "admin_name": "Admin",
        "admin_email": existing.email})
    assert response.status_code == 409


def test_organisation_request_response_never_reveals_duplicates(fx, super_admin):
    _, admin_headers = super_admin
    name = unique("Requested Org")
    payload = {"organisation_name": name, "contact_name": "Rita", "contact_email": "rita@example.com",
               "message": "We would like a workspace."}
    first = client.post("/api/org/requests", json=payload)
    duplicate = client.post("/api/org/requests", json={**payload, "organisation_name": name.upper()})
    assert first.status_code == duplicate.status_code == 202
    assert first.json() == duplicate.json() == {"status": "received"}
    with SessionLocal() as db:
        rows = db.query(Organization).filter(Organization.name.ilike(name)).all()
        assert len(rows) == 1 and rows[0].status == "requested"
        fx.track_org(rows[0].id)
        org_id = rows[0].id

    listed = client.get("/api/admin/organisations?status=requested", headers=admin_headers).json()
    item = next(entry for entry in listed if entry["id"] == org_id)
    assert item["request_message"] == "We would like a workspace." and item["active_code"] is None

    approved = client.post(f"/api/admin/organisations/{org_id}/approve", headers=admin_headers,
                           json={"admin_name": "Rita", "admin_email": f"{unique('rita')}@example.com"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["organisation"]["status"] == "pending_activation"
    assert approved.json()["activation_code"].startswith("CLY-")
    # Approving twice or rejecting a pending organisation is not a valid transition.
    assert client.post(f"/api/admin/organisations/{org_id}/approve", headers=admin_headers,
                       json={"admin_name": "Rita", "admin_email": "x@example.com"}).status_code == 409
    assert client.post(f"/api/admin/organisations/{org_id}/reject", headers=admin_headers).status_code == 409


def test_organisation_requests_are_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "ORG_REQUEST_RATE_LIMIT_PER_HOUR", 1)
    payload = {"organisation_name": unique("Limited"), "contact_name": "Lim", "contact_email": "l@example.com"}
    assert client.post("/api/org/requests", json=payload).status_code == 202
    assert client.post("/api/org/requests", json=payload).status_code == 429
    with SessionLocal() as db:
        db.query(Organization).filter(Organization.name == payload["organisation_name"]).delete()
        db.commit()
