"""
Create an individual user account when public sign-up is closed (staging: REGISTRATION_ENABLED=False).

The password is typed at a hidden prompt (twice), so it never appears in shell history or logs. For
automated test runs only, it can be passed in the CREATE_USER_PASSWORD environment variable.
The same rules as the sign-up form apply (name 2-100 characters, password 8-72 UTF-8 bytes).

Usage (repository root, or inside the backend container)
--------------------------------------------------------
    python backend/scripts/create_user.py tester@example.com "Test User"
    docker compose exec backend python backend/scripts/create_user.py tester@example.com "Test User"
"""
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pydantic import ValidationError  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models.user import User  # noqa: E402
from backend.app.schemas.auth import UserRegister  # noqa: E402
from backend.app.security.auth import hash_password  # noqa: E402


class AccountError(ValueError):
    """The account cannot be created; the message is safe to show."""


def create_individual_user(db, email: str, name: str, password: str) -> User:
    try:
        data = UserRegister(email=email, name=name, password=password)
    except ValidationError as exc:
        fields = sorted({str(err["loc"][-1]) for err in exc.errors()})
        raise AccountError(f"invalid {', '.join(fields)} (name 2-100 characters, password 8-72 bytes)") from None
    address = data.email.lower()
    if db.query(User).filter(User.email == address).first():
        raise AccountError("an account with this e-mail already exists")
    user = User(
        email=address,
        name=data.name.strip(),
        password_hash=hash_password(data.password),
        is_admin=False,
        role="consultant",
        groups=[settings.DEFAULT_ACCESS_GROUP],
        account_type="individual",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _read_password() -> str:
    automated = os.environ.get("CREATE_USER_PASSWORD")
    if automated:
        return automated
    first = getpass.getpass("Password for the new account: ")
    if getpass.getpass("Repeat the password: ") != first:
        raise AccountError("the passwords do not match")
    return first


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__)
        return 2
    email, name = args
    db = SessionLocal()
    try:
        user = create_individual_user(db, email, name, _read_password())
    except AccountError as exc:
        print(f"Not created: {exc}.")
        return 1
    finally:
        db.close()
    print(f"Created individual account {user.email} (id {user.id}). It can sign in now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
