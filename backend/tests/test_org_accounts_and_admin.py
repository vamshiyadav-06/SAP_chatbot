"""Organisation Portal account rules, organisation administration and Super Admin management
(docs/ORGANISATION_PORTAL.md). Runs against the *_test database (conftest.py)."""

import logging

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.organization import Organization
from backend.app.models.user import User
from backend.tests.org_helpers import PASSWORD, OrgFixtures, headers_for, random_password, unique

client = TestClient(app)
NOT_ACTIVE = "This account is not active. Contact your administrator."


@pytest.fixture
def fx():
    fixtures = OrgFixtures()
    yield fixtures
    fixtures.cleanup()


def _set(model, row_id, **values):
    with SessionLocal() as db:
        row = db.get(model, row_id)
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()


def _token_version(user_id):
    with SessionLocal() as db:
        return db.get(User, user_id).token_version


# ---------------------------------------------------------------------------- sign-in and account state

def test_each_portal_signs_in_only_its_own_account_type(fx):
    org = fx.organisation()
    member = fx.user(org=org, role="member")
    individual = fx.user()

    wrong_portal = client.post("/api/org/auth/login", json={"email": individual.email, "password": PASSWORD})
    assert wrong_portal.status_code == 403
    assert wrong_portal.json()["detail"] == "Sign in with your individual account at /login."
    org_at_individual = client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    assert org_at_individual.status_code == 403
    assert org_at_individual.json()["detail"] == "This is an organisation account. Sign in through the Organisation Portal."
    bad_password = client.post("/api/org/auth/login", json={"email": member.email, "password": "wrong-password-1"})
    assert bad_password.status_code == 401

    ok = client.post("/api/org/auth/login", json={"email": member.email.upper(), "password": PASSWORD})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["account_type"] == "organisation"
    assert ok.json()["user"]["organization_name"] == org.name
    with SessionLocal() as db:
        assert db.get(User, member.id).last_login_at is not None
    individual_ok = client.post("/api/auth/login", json={"email": individual.email, "password": PASSWORD})
    assert individual_ok.status_code == 200
    assert individual_ok.json()["user"]["account_type"] == "individual"
    assert individual_ok.json()["user"]["organization_id"] is None


def test_inactive_accounts_cannot_sign_in_and_their_tokens_are_rejected(fx):
    individual = fx.user()
    headers = headers_for(individual.id)
    assert client.get("/api/chats", headers=headers).status_code == 200
    _set(User, individual.id, is_active=False)  # token_version unchanged: get_current_user must still refuse
    assert client.get("/api/chats", headers=headers).status_code == 401
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    denied = client.post("/api/auth/login", json={"email": individual.email, "password": PASSWORD})
    assert (denied.status_code, denied.json()["detail"]) == (403, NOT_ACTIVE)
    # A wrong password still gets the ordinary 401 (account state is revealed only after a correct password).
    assert client.post("/api/auth/login", json={"email": individual.email, "password": "nope-nope-nope"}).status_code == 401


@pytest.mark.parametrize("org_status", ["suspended", "deactivated", "pending_activation"])
def test_members_of_inactive_organisations_are_locked_out(fx, org_status):
    org = fx.organisation()
    member = fx.user(org=org, role="owner")
    headers = headers_for(member.id)
    assert client.get("/api/org/me", headers=headers).status_code == 200
    _set(Organization, org.id, status=org_status)
    assert client.get("/api/org/me", headers=headers).status_code == 401
    assert client.get("/api/chats", headers=headers).status_code == 401
    denied = client.post("/api/org/auth/login", json={"email": member.email, "password": PASSWORD})
    assert (denied.status_code, denied.json()["detail"]) == (403, NOT_ACTIVE)


def test_pending_password_change_limits_the_api_until_changed(fx):
    org = fx.organisation()
    member = fx.user(org=org, role="member", must_change_password=True)
    old = headers_for(member.id)
    me = client.get("/api/auth/me", headers=old)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    for method, path in (("get", "/api/chats"), ("get", "/api/org/me"), ("get", "/api/org/knowledge"),
                         ("get", "/api/auth/me/export")):
        response = getattr(client, method)(path, headers=old)
        assert (response.status_code, response.json()["detail"]) == (403, "Password change required."), path

    wrong = client.post("/api/auth/change-password", headers=old,
                        json={"current_password": "not-the-password", "new_password": random_password()})
    assert wrong.status_code == 400
    same = client.post("/api/auth/change-password", headers=old,
                       json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 400
    short = client.post("/api/auth/change-password", headers=old,
                        json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422

    new_password = random_password()
    changed = client.post("/api/auth/change-password", headers=old,
                          json={"current_password": PASSWORD, "new_password": new_password})
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False
    new = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=old).status_code == 401  # old tokens revoked
    assert client.get("/api/org/me", headers=new).status_code == 200
    assert client.post("/api/org/auth/login", json={"email": member.email, "password": new_password}).status_code == 200


def test_individual_users_can_change_password_too(fx):
    individual = fx.user()
    response = client.post("/api/auth/change-password", headers=headers_for(individual.id),
                           json={"current_password": PASSWORD, "new_password": random_password()})
    assert response.status_code == 200
    assert response.json()["user"]["account_type"] == "individual"


def test_logout_is_allowed_during_a_pending_password_change(fx):
    member = fx.user(org=fx.organisation(), role="member", must_change_password=True)
    headers = headers_for(member.id)
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


# ---------------------------------------------------------------------------- organisation administrators

@pytest.fixture
def org_team(fx):
    org = fx.organisation()
    owner = fx.user(org=org, role="owner")
    admin = fx.user(org=org, role="admin")
    member = fx.user(org=org, role="member")
    return org, owner, admin, member


def test_admin_creates_a_member_with_the_email_and_password_they_choose(fx, org_team, caplog):
    caplog.set_level(logging.DEBUG)
    org, owner, admin, _ = org_team
    email = f"{unique('new-member')}@Example.com"
    chosen = random_password()
    created = client.post("/api/org/admin/members", headers=headers_for(admin.id),
                          json={"name": "New Member", "email": email, "password": chosen, "org_role": "member"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert set(body) == {"member"}, "the password the admin typed is never sent back"
    member = body["member"]
    assert member["email"] == email.lower() and member["org_role"] == "member"
    assert member["must_change_password"] is True and member["is_active"] is True
    assert set(member) == {"id", "name", "email", "org_role", "is_active", "must_change_password", "created_at",
                           "last_login_at"}
    assert chosen not in caplog.text

    login = client.post("/api/org/auth/login", json={"email": email, "password": chosen})
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    listed = client.get("/api/org/admin/members", headers=headers_for(admin.id)).json()
    assert member["id"] in {row["id"] for row in listed}
    assert not {"password", "password_hash", "temporary_password"} & {key for row in listed for key in row}

    duplicate = client.post("/api/org/admin/members", headers=headers_for(owner.id),
                            json={"name": "Again", "email": email, "password": random_password(), "org_role": "member"})
    assert duplicate.status_code == 409


@pytest.mark.parametrize("password", [None, "", "short-pw-11", "é" * 37])
def test_a_new_member_needs_a_valid_password(fx, org_team, password):
    _, owner, _, _ = org_team
    body = {"name": "New Member", "email": f"{unique('pw')}@example.com", "org_role": "member"}
    if password is not None:
        body["password"] = password
    response = client.post("/api/org/admin/members", headers=headers_for(owner.id), json=body)
    assert response.status_code == 422, "12-72 characters and at most 72 UTF-8 bytes, like every organisation password"


def test_role_rules_for_member_management(fx, org_team):
    _, owner, admin, member = org_team
    as_admin, as_owner = headers_for(admin.id), headers_for(owner.id)
    # Only the owner grants the admin role.
    assert client.post("/api/org/admin/members", headers=as_admin, json={
        "name": "Wannabe", "email": f"{unique('w')}@example.com", "password": random_password(),
        "org_role": "admin"}).status_code == 403
    assert client.patch(f"/api/org/admin/members/{member.id}", headers=as_admin,
                        json={"org_role": "admin"}).status_code == 403
    # Nobody changes themselves or the owner; admins cannot manage other admins.
    assert client.patch(f"/api/org/admin/members/{admin.id}", headers=as_admin, json={"is_active": False}).status_code == 400
    assert client.patch(f"/api/org/admin/members/{owner.id}", headers=as_admin, json={"is_active": False}).status_code == 403
    assert client.patch(f"/api/org/admin/members/{owner.id}", headers=as_owner, json={"org_role": "member"}).status_code == 400
    assert client.post(f"/api/org/admin/members/{owner.id}/reset-password", headers=as_admin,
                       json={"password": random_password()}).status_code == 403
    # A regular member has no admin access at all.
    assert client.get("/api/org/admin/members", headers=headers_for(member.id)).status_code == 403
    assert client.get("/api/org/admin/activity", headers=headers_for(member.id)).status_code == 403

    before = _token_version(member.id)
    promoted = client.patch(f"/api/org/admin/members/{member.id}", headers=as_owner, json={"org_role": "admin"})
    assert promoted.status_code == 200 and promoted.json()["org_role"] == "admin"
    assert _token_version(member.id) == before + 1  # role change revokes sessions


def test_deactivation_and_password_reset_revoke_sessions(fx, org_team):
    _, owner, admin, member = org_team
    member_headers = headers_for(member.id)
    assert client.get("/api/org/me", headers=member_headers).status_code == 200
    deactivated = client.patch(f"/api/org/admin/members/{member.id}", headers=headers_for(admin.id),
                               json={"is_active": False})
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False
    assert client.get("/api/org/me", headers=member_headers).status_code == 401
    assert client.post("/api/org/auth/login", json={"email": member.email, "password": PASSWORD}).status_code == 403
    client.patch(f"/api/org/admin/members/{member.id}", headers=headers_for(admin.id), json={"is_active": True})

    fresh = headers_for(member.id)
    too_short = client.post(f"/api/org/admin/members/{member.id}/reset-password", headers=headers_for(admin.id),
                            json={"password": "short-pw-11"})
    assert too_short.status_code == 422
    assert client.get("/api/org/me", headers=fresh).status_code == 200, "a rejected reset changes nothing"

    chosen = random_password()
    reset = client.post(f"/api/org/admin/members/{member.id}/reset-password", headers=headers_for(admin.id),
                        json={"password": chosen})
    assert reset.status_code == 200, reset.text
    assert chosen not in reset.text and not {"password", "temporary_password"} & set(reset.json())
    assert reset.json()["id"] == member.id and reset.json()["must_change_password"] is True
    assert client.get("/api/org/me", headers=fresh).status_code == 401
    assert client.post("/api/org/auth/login", json={"email": member.email, "password": PASSWORD}).status_code == 401
    relogin = client.post("/api/org/auth/login", json={"email": member.email, "password": chosen})
    assert relogin.status_code == 200 and relogin.json()["user"]["must_change_password"] is True


def test_owner_cannot_delete_own_account_but_members_can(fx, org_team):
    _, owner, _, member = org_team
    blocked = client.delete("/api/auth/me", headers=headers_for(owner.id))
    assert blocked.status_code == 409
    with SessionLocal() as db:
        assert db.get(User, owner.id) is not None
    assert client.delete("/api/auth/me", headers=headers_for(member.id)).status_code == 204


def test_organisation_admins_cannot_reach_other_organisations_members(fx, org_team):
    _, owner, _, _ = org_team
    other_org = fx.organisation()
    outsider = fx.user(org=other_org, role="member")
    individual = fx.user()
    for target in (outsider, individual):
        assert client.patch(f"/api/org/admin/members/{target.id}", headers=headers_for(owner.id),
                            json={"is_active": False}).status_code == 404
        assert client.post(f"/api/org/admin/members/{target.id}/reset-password", headers=headers_for(owner.id),
                           json={"password": random_password()}).status_code == 404
    listed = {row["id"] for row in client.get("/api/org/admin/members", headers=headers_for(owner.id)).json()}
    assert outsider.id not in listed and individual.id not in listed
    activity = client.get("/api/org/admin/activity", headers=headers_for(owner.id)).json()
    assert outsider.id not in {row["id"] for row in activity["members"]}
    with SessionLocal() as db:
        assert db.get(User, outsider.id).is_active is True


def test_activity_counts_and_organisation_settings(fx, org_team):
    org, owner, admin, member = org_team
    fx.liked_answer(member)
    activity = client.get("/api/org/admin/activity", headers=headers_for(admin.id))
    assert activity.status_code == 200
    rows = {row["id"]: row for row in activity.json()["members"]}
    assert rows[member.id]["chats"] == 1 and rows[member.id]["questions"] == 1
    assert set(rows[member.id]) == {"id", "name", "chats", "questions", "shared_answers", "comments", "likes",
                                    "last_login_at"}
    assert activity.json()["totals"]["members"] == 3 and activity.json()["totals"]["questions"] == 1

    taken = fx.organisation()
    conflict = client.patch("/api/org/admin/organisation", headers=headers_for(owner.id),
                            json={"name": taken.name.upper()})
    assert conflict.status_code == 409
    new_name = unique("Renamed Org")
    renamed = client.patch("/api/org/admin/organisation", headers=headers_for(admin.id),
                           json={"name": new_name, "contact_email": "Team@Example.com"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == new_name and renamed.json()["contact_email"] == "team@example.com"
    assert client.patch("/api/org/admin/organisation", headers=headers_for(member.id),
                        json={"name": "x" * 10}).status_code == 403


# ---------------------------------------------------------------------------- Super Admin

@pytest.fixture
def super_admin(fx):
    admin = fx.user(is_admin=True)
    return admin, headers_for(admin.id)


SUPER_ADMIN_ENDPOINTS = [
    ("get", "/api/admin/organisations", None),
    ("post", "/api/admin/organisations", {"name": "X Org", "contact_email": "a@example.com", "admin_name": "Ad",
                                          "admin_email": "b@example.com"}),
    ("get", "/api/admin/organisations/{org}", None),
    ("post", "/api/admin/organisations/{org}/approve", {"admin_name": "Ad", "admin_email": "b@example.com"}),
    ("post", "/api/admin/organisations/{org}/reject", None),
    ("post", "/api/admin/organisations/{org}/activation-codes", None),
    ("patch", "/api/admin/organisations/{org}/status", {"status": "suspended"}),
    ("get", "/api/admin/individual-users", None),
    ("patch", "/api/admin/users/{user}/status", {"is_active": False}),
]


def test_super_admin_endpoints_reject_everyone_else(fx, org_team):
    org, owner, _, _ = org_team
    individual = fx.user()
    for caller in (owner, individual, None):
        headers = headers_for(caller.id) if caller else {}
        for method, path, body in SUPER_ADMIN_ENDPOINTS:
            url = path.format(org=org.id, user=individual.id)
            kwargs = {"json": body} if body is not None else {}
            response = getattr(client, method)(url, headers=headers, **kwargs)
            assert response.status_code in (401, 403), (url, caller and caller.org_role, response.status_code)
    with SessionLocal() as db:
        assert db.get(Organization, org.id).status == "active"
        assert db.get(User, individual.id).is_active is True


def test_status_transitions_and_session_revocation(fx, super_admin, org_team):
    _, admin_headers = super_admin
    org, owner, _, member = org_team
    member_headers = headers_for(member.id)
    before = _token_version(member.id)
    suspended = client.patch(f"/api/admin/organisations/{org.id}/status", headers=admin_headers,
                             json={"status": "suspended"})
    assert suspended.status_code == 200 and suspended.json()["status"] == "suspended"
    assert _token_version(member.id) == before + 1
    assert client.get("/api/org/me", headers=member_headers).status_code == 401
    assert client.patch(f"/api/admin/organisations/{org.id}/status", headers=admin_headers,
                        json={"status": "active"}).json()["status"] == "active"
    assert client.get("/api/org/me", headers=headers_for(member.id)).status_code == 200

    pending = fx.organisation(status="pending_activation")
    requested = fx.organisation(status="requested")
    assert client.patch(f"/api/admin/organisations/{pending.id}/status", headers=admin_headers,
                        json={"status": "active"}).status_code == 409  # activation needs the code
    assert client.patch(f"/api/admin/organisations/{requested.id}/status", headers=admin_headers,
                        json={"status": "suspended"}).status_code == 409
    assert client.patch(f"/api/admin/organisations/{org.id}/status", headers=admin_headers,
                        json={"status": "rejected"}).status_code == 422
    assert client.patch(f"/api/admin/organisations/{requested.id}/status", headers=admin_headers,
                        json={"status": "active"}).status_code == 409
    assert client.post(f"/api/admin/organisations/{requested.id}/reject", headers=admin_headers).json()["status"] == "rejected"
    assert client.get("/api/admin/organisations/does-not-exist", headers=admin_headers).status_code == 404


def test_organisation_detail_and_listing(fx, super_admin, org_team):
    _, admin_headers = super_admin
    org, owner, admin, member = org_team
    fx.liked_answer(member)
    detail = client.get(f"/api/admin/organisations/{org.id}", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["organisation"]["id"] == org.id and body["organisation"]["member_count"] == 3
    assert {row["org_role"] for row in body["admins"]} == {"owner", "admin"}
    assert member.email not in {row["email"] for row in body["admins"]}
    assert body["usage"] == {"members": 3, "active_members": 3, "questions_30d": 1, "shared_answers": 0, "comments": 0}
    listing = client.get("/api/admin/organisations?status=active", headers=admin_headers).json()
    assert org.id in {row["id"] for row in listing}
    assert all(row["status"] == "active" for row in listing)
    assert client.get("/api/admin/organisations?status=bogus", headers=admin_headers).status_code == 422


def test_individual_user_management(fx, super_admin, org_team):
    admin, admin_headers = super_admin
    _, owner, _, _ = org_team
    individual = fx.user(name=unique("Indy"))
    listed = client.get(f"/api/admin/individual-users?search={individual.name}", headers=admin_headers).json()
    assert listed["total"] == 1 and listed["users"][0]["id"] == individual.id
    assert set(listed["users"][0]) == {"id", "name", "email", "is_admin", "is_active", "created_at", "last_login_at",
                                       "chats", "questions"}
    org_search = client.get(f"/api/admin/individual-users?search={owner.email}", headers=admin_headers).json()
    assert org_search["total"] == 0  # organisation accounts are listed under their organisation

    individual_headers = headers_for(individual.id)
    off = client.patch(f"/api/admin/users/{individual.id}/status", headers=admin_headers, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert client.get("/api/chats", headers=individual_headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": individual.email, "password": PASSWORD}).status_code == 403
    on = client.patch(f"/api/admin/users/{individual.id}/status", headers=admin_headers, json={"is_active": True})
    assert on.status_code == 200 and on.json()["is_active"] is True

    assert client.patch(f"/api/admin/users/{owner.id}/status", headers=admin_headers,
                        json={"is_active": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{admin.id}/status", headers=admin_headers,
                        json={"is_active": False}).status_code == 400
    assert client.patch("/api/admin/users/missing/status", headers=admin_headers,
                        json={"is_active": False}).status_code == 404


# ---------------------------------------------------------------------------- admin creates individual users

def test_admin_creates_an_individual_user_who_can_sign_in(fx):
    admin = fx.user(is_admin=True)
    headers = headers_for(admin.id)
    email = f"{unique('created')}@example.com"
    body = {"name": "Created Person", "email": email.upper(), "password": "Starter-Pass-1"}

    created = client.post("/api/admin/individual-users", headers=headers, json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    fx.track_user(data["id"])
    assert data["email"] == email and data["is_active"] is True and data["is_admin"] is False
    assert "password" not in data and "password_hash" not in data

    login = client.post("/api/auth/login", json={"email": email, "password": "Starter-Pass-1"})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["account_type"] == "individual"

    duplicate = client.post("/api/admin/individual-users", headers=headers, json=body)
    assert duplicate.status_code == 409


def test_creating_individual_users_needs_an_admin_and_a_valid_password(fx):
    plain = fx.user()
    body = {"name": "Nope Person", "email": f"{unique('nope')}@example.com", "password": "Starter-Pass-1"}
    assert client.post("/api/admin/individual-users", json=body).status_code in (401, 403)
    assert client.post("/api/admin/individual-users", headers=headers_for(plain.id), json=body).status_code == 403
    admin = fx.user(is_admin=True)
    short = client.post("/api/admin/individual-users", headers=headers_for(admin.id), json={**body, "password": "short"})
    assert short.status_code == 422
