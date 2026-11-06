import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.refresh_token import RefreshToken
from backend.app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password exceeds the bcrypt 72-byte limit")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """A real bcrypt hash of a random password, used when the account does not exist."""
    return hash_password(secrets.token_urlsafe(24))


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Look up and verify a user. Exactly one bcrypt check runs whether or not the email exists, so
    response time does not reveal which accounts exist (AUDIT_REPORT F-39)."""
    user = db.query(User).filter(User.email == (email or "").lower()).first()
    password_ok = verify_password(password, user.password_hash if user else _dummy_password_hash())
    return user if (user is not None and password_ok) else None

REQUIRED_CLAIMS = ["exp", "iat", "sub", "ver", "iss", "aud", "jti"]


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Signed access token: subject, token version, issuer, audience and a unique id. No personal data
    such as the e-mail address is put in the (readable) payload (AUDIT_REPORT F-40)."""
    now = datetime.now(timezone.utc)
    to_encode = {key: value for key, value in data.items() if key in ("sub", "ver")}
    to_encode.setdefault("ver", 0)
    to_encode.update({
        "exp": now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)),
        "iat": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": uuid.uuid4().hex,
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify signature, pinned algorithm, expiry, issuer and audience; raises jwt.PyJWTError."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={"require": REQUIRED_CLAIMS},
    )


ORGANISATION_ACCOUNT_TYPE = "organisation"
PASSWORD_CHANGE_REQUIRED = "Password change required."


def account_is_usable(user) -> bool:
    """Inactive accounts, and organisation accounts whose organisation is not active, cannot use the
    API (docs/ORGANISATION_PORTAL.md). Attributes are read defensively: tests use lightweight principals."""
    if getattr(user, "is_active", True) is False:
        return False
    if getattr(user, "account_type", None) == ORGANISATION_ACCOUNT_TYPE:
        organization = getattr(user, "organization", None)
        return organization is not None and organization.status == "active"
    return True


def password_change_pending(user) -> bool:
    return bool(getattr(user, "must_change_password", False))


def _user_for_token(token: str, db: Session) -> Optional[User]:
    """The token's user if the token is valid, not revoked (token_version matches) and the account
    may still sign in (active, and for organisation accounts an active organisation)."""
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or payload.get("ver") != user.token_version:
        return None
    if not account_is_usable(user):
        return None
    return user


def user_for_access_token(token: str, db: Session) -> Optional[User]:
    """Public form of _user_for_token for endpoints that accept more than one credential (logout)."""
    return _user_for_token(token, db)


# --------------------------------------------------------------------------------------------------
# Refresh tokens (models/refresh_token.py): an HttpOnly cookie scoped to /api/auth, rotated on every use
# --------------------------------------------------------------------------------------------------

REFRESH_COOKIE_PATH = f"{settings.API_V1_STR}/auth"
# Browsers cannot add a custom header to a cross-site form post, and cross-origin fetches with it need a
# CORS preflight, so requiring it (with SameSite=Strict) blocks cross-site refresh requests.
REFRESH_REQUEST_HEADER = "X-Refresh-Request"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(db: Session, user: User, *, family_id: Optional[str] = None,
                        expires_at: Optional[datetime] = None) -> tuple[str, RefreshToken]:
    """Add (not commit) a refresh token row; returns the raw token for the cookie and the row. Without
    `family_id` a new family (a new sign-in) starts; rotations pass the family and its original expiry."""
    raw = secrets.token_urlsafe(32)  # 256 bits
    now = _utcnow()
    row = RefreshToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        family_id=family_id or str(uuid.uuid4()),
        token_hash=hash_refresh_token(raw),
        token_version=user.token_version or 0,
        created_at=now,
        expires_at=expires_at or now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(row)
    return raw, row


def revoke_refresh_family(db: Session, family_id: str) -> None:
    (db.query(RefreshToken)
     .filter(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
     .update({RefreshToken.revoked_at: _utcnow()}, synchronize_session=False))


def revoke_user_refresh_tokens(db: Session, user_id: str) -> None:
    (db.query(RefreshToken)
     .filter(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
     .update({RefreshToken.revoked_at: _utcnow()}, synchronize_session=False))


def find_refresh_token(db: Session, raw: Optional[str], *, lock: bool = False) -> Optional[RefreshToken]:
    if not raw:
        return None
    query = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw))
    return (query.with_for_update() if lock else query).first()


@dataclass
class RefreshResult:
    """`user` and `raw` are set on success; otherwise `reason` says why (audit log only, never the client)."""
    user: Optional[User] = None
    raw: Optional[str] = None
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None


def rotate_refresh_token(db: Session, raw: Optional[str]) -> RefreshResult:
    """Validate the presented token and rotate it within its family; commits.

    Fails when the token is unknown, revoked or expired, when the user's token_version changed (password
    change, logout, reset, deactivation) or the account may no longer sign in. A token that was already
    rotated is accepted again only within REFRESH_TOKEN_REUSE_GRACE_SECONDS (two tabs refreshing at the
    same moment get sibling tokens); later, it is treated as stolen and its whole family is revoked."""
    row = find_refresh_token(db, raw, lock=True)  # the lock serialises concurrent rotations of one token
    if row is None:
        db.rollback()
        return RefreshResult(reason="missing" if not raw else "unknown")
    now = _utcnow()
    if row.revoked_at is not None:
        db.rollback()
        return RefreshResult(reason="revoked")
    if row.expires_at <= now:
        db.rollback()
        return RefreshResult(reason="expired")
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or user.token_version != row.token_version or not account_is_usable(user):
        revoke_refresh_family(db, row.family_id)
        db.commit()
        return RefreshResult(reason="session_revoked")
    if row.rotated_at is not None:
        if now - row.rotated_at > timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS):
            revoke_refresh_family(db, row.family_id)
            db.commit()
            return RefreshResult(reason="reuse_detected")
        new_raw, _ = issue_refresh_token(db, user, family_id=row.family_id, expires_at=row.expires_at)
    else:
        new_raw, new_row = issue_refresh_token(db, user, family_id=row.family_id, expires_at=row.expires_at)
        row.rotated_at = now
        row.replaced_by_id = new_row.id
    expires_at = row.expires_at
    db.commit()
    return RefreshResult(user=user, raw=new_raw, expires_at=expires_at)


def _refresh_cookie_options() -> dict:
    return {
        "path": REFRESH_COOKIE_PATH,
        "httponly": True,
        "samesite": "strict",
        "secure": settings.ENVIRONMENT.lower() == "production",
    }


def set_refresh_cookie(response: Response, raw: str, expires_at: Optional[datetime] = None) -> None:
    """Max-Age is REFRESH_TOKEN_EXPIRE_DAYS on sign-in; after a rotation, what is left of the session."""
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600
    if expires_at is not None:
        max_age = max(0, min(max_age, int((expires_at - _utcnow()).total_seconds())))
    response.set_cookie(settings.REFRESH_COOKIE_NAME, raw, max_age=max_age, **_refresh_cookie_options())


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, **_refresh_cookie_options())


def start_refresh_session(db: Session, user: User, response: Response) -> None:
    """A successful sign-in (or a session re-issued after a password change): a new family and cookie."""
    raw, _ = issue_refresh_token(db, user)
    db.commit()
    set_refresh_cookie(response, raw)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_allow_password_change(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """The signed-in user even while a password change is pending. Only GET /auth/me, POST /auth/logout
    and POST /auth/change-password use this; everything else goes through get_current_user."""
    if not token:
        raise _credentials_exception()
    user = _user_for_token(token, db)
    if user is None:
        raise _credentials_exception()
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    user = get_current_user_allow_password_change(token=token, db=db)
    if password_change_pending(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    return user

def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    user = _user_for_token(token, db)
    if user is None or password_change_pending(user):
        return None
    return user

def admin_key_matches(candidate: Optional[str]) -> bool:
    """X-Admin-Key check in constant time. An unset ADMIN_API_KEY disables key access entirely."""
    configured = settings.ADMIN_API_KEY
    if not configured or not candidate:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), configured.encode("utf-8"))

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires administrator privileges."
        )
    return current_user

def verify_admin_key_or_user(
    request: Request,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """A valid X-Admin-Key ("admin_key") or an admin user; 403 otherwise. Key use is audited (F-25)."""
    if admin_key_matches(x_admin_key):
        from backend.app.services import audit_log
        audit_log.record("admin_key_used", request=request, actor_type="admin_key", target=request.url.path)
        return "admin_key"
    if token:
        user = _user_for_token(token, db)
        if user is not None and user.is_admin and not password_change_pending(user):
            return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Admin access required."
    )
