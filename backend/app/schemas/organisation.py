"""Request bodies for the Organisation Portal (docs/ORGANISATION_PORTAL.md). Responses are built in the
API modules as plain dictionaries matching the documented shapes."""

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.app.schemas.auth import check_password_bytes
from backend.app.services.org_categoriser import CATEGORY_KEYS

CategoryKey = Literal[CATEGORY_KEYS]  # type: ignore[valid-type]


def _clean_text(value, minimum: int):
    """Trim surrounding whitespace; the trimmed value must still meet the minimum length."""
    if isinstance(value, str):
        value = value.strip()
        if len(value) < minimum:
            raise ValueError(f"Must contain at least {minimum} non-space characters")
    return value


def _lower_email(value):
    return value.strip().lower() if isinstance(value, str) else value


class OrgRequestIn(BaseModel):
    organisation_name: str = Field(..., min_length=2, max_length=120)
    contact_name: str = Field(..., min_length=2, max_length=120)
    contact_email: EmailStr = Field(..., max_length=255)
    message: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("organisation_name", "contact_name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("contact_email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class ActivationCodeIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)


class ActivationCompleteIn(ActivationCodeIn):
    name: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=12, max_length=72)

    @field_validator("name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("password")
    @classmethod
    def bcrypt_byte_limit(cls, v):
        return check_password_bytes(v)


class ShareAnswerIn(BaseModel):
    message_id: str = Field(..., min_length=1, max_length=36)


class CategoryUpdateIn(BaseModel):
    category: CategoryKey


class CommentIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 1)


class MemberPasswordIn(BaseModel):
    """A password the organisation admin chooses for a member (first password or reset). Same rule as every
    organisation password; the member still chooses their own at the next sign-in (must_change_password)."""
    password: str = Field(..., min_length=12, max_length=72)

    @field_validator("password")
    @classmethod
    def bcrypt_byte_limit(cls, v):
        return check_password_bytes(v)


class MemberCreateIn(MemberPasswordIn):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr = Field(..., max_length=255)
    org_role: Literal["admin", "member"] = "member"

    @field_validator("name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class MemberUpdateIn(BaseModel):
    org_role: Optional[Literal["admin", "member"]] = None
    is_active: Optional[bool] = None


class OrganisationUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    contact_email: Optional[EmailStr] = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("contact_email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class OrganisationCreateIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    contact_email: EmailStr = Field(..., max_length=255)
    contact_name: Optional[str] = Field(default=None, max_length=120)
    admin_name: str = Field(..., min_length=2, max_length=120)
    admin_email: EmailStr = Field(..., max_length=255)

    @field_validator("name", "admin_name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("contact_email", "admin_email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class OrganisationApproveIn(BaseModel):
    admin_name: str = Field(..., min_length=2, max_length=120)
    admin_email: EmailStr = Field(..., max_length=255)

    @field_validator("admin_name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("admin_email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class ActivationCodeReissueIn(BaseModel):
    """Optional: by default the new code goes to the same administrator as the previous one."""
    admin_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    admin_email: Optional[EmailStr] = Field(default=None, max_length=255)

    @field_validator("admin_name")
    @classmethod
    def strip_text(cls, v):
        return _clean_text(v, 2)

    @field_validator("admin_email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)


class OrganisationStatusIn(BaseModel):
    status: Literal["active", "suspended", "deactivated"]


class IndividualUserCreateIn(BaseModel):
    """Super Admin creates an individual account; same name and password rules as public sign-up."""

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v):
        return _clean_text(v, 2)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v):
        return _lower_email(v)

    @field_validator("password")
    @classmethod
    def bcrypt_byte_limit(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return v


class UserStatusIn(BaseModel):
    is_active: bool
