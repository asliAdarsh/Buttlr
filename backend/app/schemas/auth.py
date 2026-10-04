"""Authentication payloads.

The frontend never asserts identity. It sends a bearer token; the backend resolves the
principal from that token alone.
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import DomainModel
from app.schemas.organization import Organization, OrgRole, User


class DevLoginRequest(DomainModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=80)


class TokenResponse(DomainModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class Principal(DomainModel):
    """Resolved caller. Built server-side from the verified token."""

    user_id: str
    email: str
    display_name: str
    photo_url: str | None = None
    organization_id: str | None = None
    role: OrgRole | None = None
    team_ids: list[str] = Field(default_factory=list)
    is_dev: bool = False


class SessionContext(DomainModel):
    user: User
    organizations: list[Organization]
    active_organization_id: str | None = None
