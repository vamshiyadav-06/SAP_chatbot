import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, Request, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db
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


def _user_for_token(token: str, db: Session) -> Optional[User]:
    """The token's user if the token is valid and not revoked (token_version matches)."""
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or payload.get("ver") != user.token_version:
        return None
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    user = _user_for_token(token, db)
    if user is None:
        raise credentials_exception
    return user

def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    return _user_for_token(token, db)

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
        if user is not None and user.is_admin:
            return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized: Admin access required."
    )
