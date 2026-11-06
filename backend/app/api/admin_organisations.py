"""Super Admin: Organisation Management and Individual User Management (docs/ORGANISATION_PORTAL.md).

Requires an administrator JWT (users.is_admin). Activation codes are returned once in the response that
issues them; only their SHA-256 hash and last four characters are stored, and neither is logged.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.chat import Chat
from backend.app.models.message import Message
from backend.app.models.organization import (
    ACCOUNT_INDIVIDUAL,
    ACCOUNT_ORGANISATION,
    ORG_MANAGER_ROLES,
    ORG_STATUS_ACTIVE,
    ORG_STATUS_DEACTIVATED,
    ORG_STATUS_PENDING,
    ORG_STATUS_REJECTED,
    ORG_STATUS_REQUESTED,
    ORG_STATUS_SUSPENDED,
    ORG_STATUSES,
    OrgAnswerComment,
    OrgSharedAnswer,
    Organization,
)
from backend.app.models.user import User
from backend.app.schemas.organisation import (
    ActivationCodeReissueIn,
    OrganisationApproveIn,
    OrganisationCreateIn,
    IndividualUserCreateIn,
    OrganisationStatusIn,
    UserStatusIn,
)
from backend.app.config import settings
from backend.app.security.auth import get_current_admin_user, hash_password
from backend.app.services import audit_log
from backend.app.services.organisations import (
    active_code,
    email_in_use,
    escape_like,
    find_organisation_by_name,
    iso,
    issue_activation_code,
    latest_code,
    member_count,
    member_counts,
    revoke_member_sessions,
    revoke_unused_codes,
    unique_slug,
    utcnow,
)

router = APIRouter(prefix="/admin", tags=["Super Admin / Organisations"])

ORGANISATION_NOT_FOUND = "Organisation not found"
NAME_TAKEN = "An organisation with this name already exists."
EMAIL_TAKEN = "An account with this e-mail address already exists."
STATUS_CHANGE_NOT_ALLOWED = "This status change is not allowed."

# Allowed PATCH /admin/organisations/{id}/status transitions. Activation itself only happens through an
# activation code, so pending/requested/rejected organisations cannot be made active here.
STATUS_TRANSITIONS = {
    ORG_STATUS_ACTIVE: {ORG_STATUS_SUSPENDED, ORG_STATUS_DEACTIVATED},
    ORG_STATUS_SUSPENDED: {ORG_STATUS_ACTIVE, ORG_STATUS_DEACTIVATED},
    ORG_STATUS_DEACTIVATED: {ORG_STATUS_ACTIVE},
    ORG_STATUS_PENDING: {ORG_STATUS_DEACTIVATED},
}


def _organisation_out(db: Session, organisation: Organization, members: Optional[int] = None) -> dict:
    code = active_code(db, organisation.id)
    return {
        "id": organisation.id,
        "name": organisation.name,
        "status": organisation.status,
        "contact_name": organisation.contact_name,
        "contact_email": organisation.contact_email,
        "member_count": member_count(db, organisation.id) if members is None else members,
        "created_at": iso(organisation.created_at),
        "activated_at": iso(organisation.activated_at),
        "request_message": organisation.request_message,
        "active_code": ({"hint": code.code_hint, "expires_at": iso(code.expires_at), "admin_email": code.admin_email}
                        if code is not None else None),
    }


def _get_organisation(db: Session, organisation_id: str) -> Organization:
    organisation = db.get(Organization, organisation_id)
    if organisation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ORGANISATION_NOT_FOUND)
    return organisation


def _require_free_email(db: Session, email: str) -> None:
    if email_in_use(db, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN)


def _issued(db: Session, organisation: Organization, plaintext: str, code) -> dict:
    return {"organisation": _organisation_out(db, organisation), "activation_code": plaintext,
            "expires_at": iso(code.expires_at)}


@router.get("/organisations")
def list_organisations(
    status_filter: Optional[str] = Query(None, alias="status"),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    query = db.query(Organization)
    if status_filter:
        if status_filter not in ORG_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown status.")
        query = query.filter(Organization.status == status_filter)
    organisations = query.order_by(Organization.created_at.desc()).all()
    counts = member_counts(db, [organisation.id for organisation in organisations])
    return [_organisation_out(db, organisation, counts.get(organisation.id, 0)) for organisation in organisations]


@router.post("/organisations", status_code=status.HTTP_201_CREATED)
def create_organisation(body: OrganisationCreateIn, request: Request, admin: User = Depends(get_current_admin_user),
                        db: Session = Depends(get_db)):
    """Create an organisation awaiting activation and issue its first activation code (shown once)."""
    if find_organisation_by_name(db, body.name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NAME_TAKEN)
    _require_free_email(db, body.admin_email)
    now = utcnow()
    organisation = Organization(
        name=body.name,
        slug=unique_slug(db, body.name),
        contact_name=(body.contact_name or "").strip() or body.admin_name,
        contact_email=body.contact_email,
        status=ORG_STATUS_PENDING,
        created_by=admin.id,
        created_at=now,
        updated_at=now,
    )
    db.add(organisation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NAME_TAKEN)
    plaintext, code = issue_activation_code(db, organisation, body.admin_name, body.admin_email, admin.id)
    db.commit()
    audit_log.record("org_create", request=request, principal=admin, target=organisation.id)
    audit_log.record("org_activation_code_issue", request=request, principal=admin, target=organisation.id,
                     details={"code_id": code.id})
    return _issued(db, organisation, plaintext, code)


@router.post("/organisations/{organisation_id}/approve")
def approve_organisation(organisation_id: str, body: OrganisationApproveIn, request: Request,
                         admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    organisation = _get_organisation(db, organisation_id)
    if organisation.status != ORG_STATUS_REQUESTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only requested organisations can be approved.")
    _require_free_email(db, body.admin_email)
    organisation.status = ORG_STATUS_PENDING
    organisation.updated_at = utcnow()
    plaintext, code = issue_activation_code(db, organisation, body.admin_name, body.admin_email, admin.id)
    db.commit()
    audit_log.record("org_approve", request=request, principal=admin, target=organisation.id)
    audit_log.record("org_activation_code_issue", request=request, principal=admin, target=organisation.id,
                     details={"code_id": code.id})
    return _issued(db, organisation, plaintext, code)


@router.post("/organisations/{organisation_id}/reject")
def reject_organisation(organisation_id: str, request: Request, admin: User = Depends(get_current_admin_user),
                        db: Session = Depends(get_db)):
    organisation = _get_organisation(db, organisation_id)
    if organisation.status != ORG_STATUS_REQUESTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only requested organisations can be rejected.")
    organisation.status = ORG_STATUS_REJECTED
    organisation.updated_at = utcnow()
    db.commit()
    audit_log.record("org_reject", request=request, principal=admin, target=organisation.id)
    return _organisation_out(db, organisation)


@router.post("/organisations/{organisation_id}/activation-codes")
def reissue_activation_code(organisation_id: str, request: Request,
                            body: Optional[ActivationCodeReissueIn] = Body(None),
                            admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Issue a new code for an organisation awaiting activation; its unused codes are revoked. The new code
    goes to the previous code's administrator unless admin_name/admin_email are given."""
    organisation = _get_organisation(db, organisation_id)
    if organisation.status != ORG_STATUS_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Activation codes can only be issued for organisations awaiting activation.")
    previous = latest_code(db, organisation.id)
    admin_name = (body.admin_name if body else None) or (previous.admin_name if previous else None)
    admin_email = (body.admin_email if body else None) or (previous.admin_email if previous else None)
    if not admin_name or not admin_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin_name and admin_email are required.")
    _require_free_email(db, admin_email)
    plaintext, code = issue_activation_code(db, organisation, admin_name, admin_email, admin.id)
    db.commit()
    audit_log.record("org_activation_code_issue", request=request, principal=admin, target=organisation.id,
                     details={"code_id": code.id, "reissue": True})
    return {"activation_code": plaintext, "expires_at": iso(code.expires_at)}


@router.patch("/organisations/{organisation_id}/status")
def change_organisation_status(organisation_id: str, body: OrganisationStatusIn, request: Request,
                               admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    organisation = _get_organisation(db, organisation_id)
    previous = organisation.status
    if body.status == previous:
        return _organisation_out(db, organisation)
    allowed = STATUS_TRANSITIONS.get(previous, set())
    if body.status not in allowed or (body.status == ORG_STATUS_ACTIVE and organisation.activated_at is None):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=STATUS_CHANGE_NOT_ALLOWED)
    organisation.status = body.status
    organisation.updated_at = utcnow()
    revoked = 0
    if body.status != ORG_STATUS_ACTIVE:
        revoked = revoke_member_sessions(db, organisation.id)
        revoke_unused_codes(db, organisation.id)
    db.commit()
    audit_log.record("org_status_change", request=request, principal=admin, target=organisation.id,
                     details={"before": previous, "after": body.status, "sessions_revoked": revoked})
    return _organisation_out(db, organisation)


@router.get("/organisations/{organisation_id}")
def organisation_detail(organisation_id: str, admin: User = Depends(get_current_admin_user),
                        db: Session = Depends(get_db)):
    """Organisation, its owner/administrators and usage counts. No chat or hub content."""
    organisation = _get_organisation(db, organisation_id)
    managers = (db.query(User).filter(User.organization_id == organisation.id, User.org_role.in_(ORG_MANAGER_ROLES))
                .order_by(User.created_at.asc()).all())
    members_query = db.query(func.count(User.id)).filter(User.organization_id == organisation.id)
    since = utcnow() - timedelta(days=30)
    questions_30d = (db.query(func.count(Message.id))
                     .join(Chat, Chat.id == Message.chat_id)
                     .join(User, User.id == Chat.user_id)
                     .filter(User.organization_id == organisation.id, Message.role == "user",
                             Message.created_at >= since)
                     .scalar())
    shared_answers = (db.query(func.count(OrgSharedAnswer.id))
                      .filter(OrgSharedAnswer.organization_id == organisation.id).scalar())
    comments = (db.query(func.count(OrgAnswerComment.id))
                .join(OrgSharedAnswer, OrgSharedAnswer.id == OrgAnswerComment.shared_answer_id)
                .filter(OrgSharedAnswer.organization_id == organisation.id).scalar())
    return {
        "organisation": _organisation_out(db, organisation),
        "admins": [{"name": user.name, "email": user.email, "org_role": user.org_role, "is_active": user.is_active,
                    "last_login_at": iso(user.last_login_at)} for user in managers],
        "usage": {
            "members": members_query.scalar() or 0,
            "active_members": members_query.filter(User.is_active.is_(True)).scalar() or 0,
            "questions_30d": questions_30d or 0,
            "shared_answers": shared_answers or 0,
            "comments": comments or 0,
        },
    }


def _individual_out(user: User, chats: dict, questions: dict) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": iso(user.created_at),
        "last_login_at": iso(user.last_login_at),
        "chats": chats.get(user.id, 0),
        "questions": questions.get(user.id, 0),
    }


def _usage_counts(db: Session, user_ids):
    if not user_ids:
        return {}, {}
    chats = dict(db.query(Chat.user_id, func.count(Chat.id)).filter(Chat.user_id.in_(user_ids))
                 .group_by(Chat.user_id).all())
    questions = dict(db.query(Chat.user_id, func.count(Message.id))
                     .join(Message, Message.chat_id == Chat.id)
                     .filter(Chat.user_id.in_(user_ids), Message.role == "user")
                     .group_by(Chat.user_id).all())
    return chats, questions


@router.get("/individual-users")
def list_individual_users(
    search: Optional[str] = Query(None, max_length=255),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.account_type == ACCOUNT_INDIVIDUAL)
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        query = query.filter(or_(User.email.ilike(pattern, escape="\\"), User.name.ilike(pattern, escape="\\")))
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    chats, questions = _usage_counts(db, [user.id for user in users])
    return {"total": total, "users": [_individual_out(user, chats, questions) for user in users]}


@router.post("/individual-users", status_code=status.HTTP_201_CREATED)
def create_individual_user(body: IndividualUserCreateIn, request: Request,
                           admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Create an individual account with a password the admin types (never returned or logged)."""
    _require_free_email(db, body.email)
    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        is_admin=False,
        role="consultant",
        groups=[settings.DEFAULT_ACCESS_GROUP],
        account_type=ACCOUNT_INDIVIDUAL,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_TAKEN)
    db.refresh(user)
    audit_log.record("user_create", request=request, principal=admin, target=user.id)
    return _individual_out(user, {}, {})


@router.patch("/users/{user_id}/status")
def change_user_status(user_id: str, body: UserStatusIn, request: Request,
                       admin: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Activate or deactivate an individual account. Deactivation revokes its sessions."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.account_type == ACCOUNT_ORGANISATION:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Organisation accounts are managed by their organisation.")
    if user.id == admin.id and not body.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account.")
    if user.is_admin and user.is_active and not body.is_active:
        other_active_admins = db.query(func.count(User.id)).filter(
            User.is_admin.is_(True), User.is_active.is_(True), User.id != user.id).scalar()
        if not other_active_admins:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="The last active administrator cannot be deactivated.")
    previous = user.is_active
    if previous != body.is_active:
        user.is_active = body.is_active
        if not body.is_active:
            user.token_version += 1
        db.commit()
        db.refresh(user)
        audit_log.record("user_status_change", request=request, principal=admin, target=user.id,
                         details={"before": previous, "after": body.is_active})
    chats, questions = _usage_counts(db, [user.id])
    return _individual_out(user, chats, questions)
