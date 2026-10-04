"""Users, organizations, members and teams."""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import DomainModel, utcnow
from app.schemas.enums import OrgRole


class UserPreferences(DomainModel):
    theme: str = "system"
    accent: str = "violet"
    density: str = "comfortable"
    email_notifications: bool = True
    in_app_notifications: bool = True
    notify_on_approval: bool = True
    notify_on_completion: bool = True
    notify_on_failure: bool = True


class User(DomainModel):
    id: str
    email: str
    display_name: str
    photo_url: str | None = None
    title: str | None = None
    default_organization_id: str | None = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime | None = None


class UserUpdate(DomainModel):
    display_name: str | None = None
    photo_url: str | None = None
    title: str | None = None
    default_organization_id: str | None = None
    preferences: UserPreferences | None = None


class OrganizationSettings(DomainModel):
    default_model: str = "auto"
    allow_local_models: bool = True
    require_approval_for_high_risk: bool = True
    data_retention_days: int = 90
    log_retention_days: int = 180
    audit_enabled: bool = True


class Organization(DomainModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    logo_emoji: str = "🏢"
    owner_id: str
    settings: OrganizationSettings = Field(default_factory=OrganizationSettings)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class OrganizationCreate(DomainModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=400)
    logo_emoji: str = "🏢"


class OrganizationUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=400)
    logo_emoji: str | None = None
    settings: OrganizationSettings | None = None


class Member(DomainModel):
    """Organization membership. Document id is the user id."""

    user_id: str
    organization_id: str
    role: OrgRole = OrgRole.MEMBER
    team_ids: list[str] = Field(default_factory=list)
    invited_by: str | None = None
    joined_at: datetime = Field(default_factory=utcnow)


class MemberWithUser(Member):
    user: User | None = None


class MemberInvite(DomainModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER
    team_ids: list[str] = Field(default_factory=list)


class MemberUpdate(DomainModel):
    role: OrgRole | None = None
    team_ids: list[str] | None = None


class Team(DomainModel):
    id: str
    organization_id: str
    name: str
    description: str | None = None
    emoji: str = "🛠️"
    color: str = "violet"
    #: Team membership, in the order people were added. Stored on the team document.
    member_ids: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TeamCreate(DomainModel):
    name: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=400)
    emoji: str = "🛠️"
    color: str = "violet"
    member_ids: list[str] = Field(default_factory=list)


class TeamUpdate(DomainModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=400)
    emoji: str | None = None
    color: str | None = None
    member_ids: list[str] | None = None


class OrgSummary(DomainModel):
    organization: Organization
    role: OrgRole
    member_count: int = 0
    team_count: int = 0
    buttlr_count: int = 0
    active_buttlr_count: int = 0
    pending_approval_count: int = 0
