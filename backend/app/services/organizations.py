"""Organizations, memberships and teams-of-record for a member.

Authorization lives here: every mutating operation resolves the caller's membership from the
store and compares role ranks before touching a document.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.database.base import Condition, Op, Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.schemas.auth import Principal
from app.schemas.common import utcnow
from app.schemas.enums import AuditAction, ButtlrStatus, NotificationKind, OrgRole
from app.schemas.organization import (
    Member,
    MemberInvite,
    MemberUpdate,
    MemberWithUser,
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    OrgSummary,
    User,
    UserPreferences,
)
from app.services.audit import AuditService
from app.services.notifications import NotificationService

logger = get_logger(__name__)

ROLE_RANK: dict[OrgRole, int] = {OrgRole.MEMBER: 0, OrgRole.ADMIN: 1, OrgRole.OWNER: 2}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _display_name_from_email(local_part: str) -> str:
    words = [word for word in re.split(r"[._\-]+", local_part) if word]
    return " ".join(word.capitalize() for word in words) or "New member"


def _as_timestamp(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else 0.0


class OrganizationService:
    def __init__(self, store: Store, audit: AuditService) -> None:
        self.store = store
        self.repo = Repository(store)
        self.audit = audit
        self.notifications = NotificationService(store)

    # ---- organizations ----------------------------------------------------

    async def create(self, principal: Principal, payload: OrganizationCreate) -> Organization:
        slug = await self._unique_slug(payload.name)
        organization = Organization(
            id=new_id(),
            name=payload.name,
            slug=slug,
            description=payload.description,
            logo_emoji=payload.logo_emoji,
            owner_id=principal.user_id,
        )
        await self.repo.save(
            Paths.ORGANIZATIONS, organization.model_dump(mode="python")
        )

        membership = Member(
            user_id=principal.user_id,
            organization_id=organization.id,
            role=OrgRole.OWNER,
            invited_by=None,
        )
        await self.repo.save_membership(
            organization.id, principal.user_id, membership.model_dump(mode="python")
        )

        user = await self.repo.get_user(principal.user_id)
        if user and not user.get("default_organization_id"):
            await self.repo.upsert_user(
                principal.user_id,
                {"default_organization_id": organization.id, "updated_at": organization.updated_at},
            )

        await self.audit.record(
            organization.id,
            AuditAction.ORGANIZATION_CREATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} created the organization {organization.name}",
            target_type="organization",
            target_id=organization.id,
        )
        logger.info("organization created id=%s owner=%s", organization.id, principal.user_id)
        return organization

    async def _unique_slug(self, name: str) -> str:
        base = slugify(name) or "organization"
        candidate = base
        suffix = 1
        while await self.repo.query_one(
            Paths.ORGANIZATIONS, [Condition("slug", Op.EQ, candidate)]
        ):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    async def list_for_user(self, user_id: str) -> list[OrgSummary]:
        memberships = await self.repo.memberships_for_user(user_id)
        memberships.sort(key=lambda row: _as_timestamp(row.get("joined_at")))
        summaries: list[OrgSummary] = []
        for raw in memberships:
            organization_id = raw.get("organization_id")
            if not organization_id:
                continue
            organization_raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
            if organization_raw is None:
                continue
            summaries.append(
                OrgSummary(
                    organization=Organization.model_validate(organization_raw),
                    role=OrgRole(raw.get("role") or OrgRole.MEMBER.value),
                    member_count=await self.repo.count(Paths.members(organization_id)),
                    team_count=await self.repo.count(Paths.teams(organization_id)),
                    buttlr_count=await self.repo.count(Paths.buttlrs(organization_id)),
                    active_buttlr_count=await self.repo.count(
                        Paths.buttlrs(organization_id),
                        [Condition("status", Op.EQ, ButtlrStatus.ACTIVE.value)],
                    ),
                    pending_approval_count=await self.repo.count(
                        Paths.approvals(organization_id), [Condition("status", Op.EQ, "pending")]
                    ),
                )
            )
        return summaries

    async def get(self, organization_id: str) -> Organization:
        raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        if raw is None:
            raise NotFoundError("Organization not found.")
        return Organization.model_validate(raw)

    async def update(
        self, principal: Principal, organization_id: str, patch: OrganizationUpdate
    ) -> Organization:
        await self.require_role(organization_id, principal.user_id, OrgRole.ADMIN)
        current = await self.get(organization_id)
        changes = patch.model_dump(mode="python", exclude_unset=True)
        updated = current.model_copy(update=changes)
        updated.updated_at = utcnow()
        if changes.get("name"):
            updated.slug = await self._unique_slug(str(changes["name"]))
        await self.repo.save(Paths.ORGANIZATIONS, updated.model_dump(mode="python"))
        await self.audit.record(
            organization_id,
            AuditAction.ORGANIZATION_UPDATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} updated the organization settings",
            target_type="organization",
            target_id=organization_id,
            metadata={"fields": sorted(changes.keys())},
        )
        return updated

    # ---- authorization ----------------------------------------------------

    async def require_membership(self, organization_id: str, user_id: str) -> Member:
        raw = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        if raw is None:
            raise NotFoundError("Organization not found.")
        membership = await self.repo.membership(organization_id, user_id)
        if membership is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        return Member.model_validate(membership)

    async def require_role(
        self, organization_id: str, user_id: str, minimum: OrgRole
    ) -> Member:
        member = await self.require_membership(organization_id, user_id)
        if ROLE_RANK.get(member.role, 0) < ROLE_RANK[minimum]:
            raise PermissionDeniedError("You do not have permission to perform this action.")
        return member

    # ---- members ----------------------------------------------------------

    async def members(self, organization_id: str) -> list[MemberWithUser]:
        await self.get(organization_id)
        rows = await self.repo.list(
            Paths.members(organization_id), order_by="joined_at", sort=Sort.ASC
        )
        return [await self._member_with_user(row) for row in rows]

    async def invite(
        self, principal: Principal, organization_id: str, payload: MemberInvite
    ) -> MemberWithUser:
        await self.require_role(organization_id, principal.user_id, OrgRole.ADMIN)
        role = OrgRole(payload.role)
        if ROLE_RANK.get(role, 0) > ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError("Only an owner can grant the owner role.")

        email = str(payload.email).strip().lower()
        existing = await self.repo.query_one(Paths.USERS, [Condition("email", Op.EQ, email)])
        if existing is None:
            existing = await self._create_placeholder_user(email)

        user_id = str(existing["id"])
        if await self.repo.membership(organization_id, user_id) is not None:
            raise ConflictError("That person is already a member of this organization.")

        membership = Member(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            team_ids=list(payload.team_ids),
            invited_by=principal.user_id,
        )
        await self.repo.save_membership(
            organization_id, user_id, membership.model_dump(mode="python")
        )
        for team_id in payload.team_ids:
            await self._add_to_team(organization_id, team_id, user_id)

        await self.audit.record(
            organization_id,
            AuditAction.MEMBER_INVITED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} invited {email} as {role.value}",
            target_type="member",
            target_id=user_id,
            metadata={"email": email, "role": role.value, "team_ids": list(payload.team_ids)},
        )
        await self.notifications.notify(
            organization_id,
            NotificationKind.MEMBER_ADDED,
            title=f"{principal.display_name} added you to their workspace",
            body=email,
            link=f"/organizations/{organization_id}/members",
            user_id=user_id,
        )
        return await self._member_with_user(membership.model_dump(mode="python"))

    async def _create_placeholder_user(self, email: str) -> dict[str, Any]:
        """Create a user document so an invited person can sign in with that email."""

        local_part = email.split("@", 1)[0][:20]
        user_id = f"{local_part}-{uuid.uuid4().hex[:6]}"
        user = User(
            id=user_id,
            email=email,
            display_name=_display_name_from_email(local_part),
            preferences=UserPreferences(),
        )
        saved = await self.repo.upsert_user(user_id, user.model_dump(mode="python"))
        logger.info("placeholder user created id=%s", user_id)
        return saved

    async def update_member(
        self,
        principal: Principal,
        organization_id: str,
        user_id: str,
        patch: MemberUpdate,
    ) -> MemberWithUser:
        actor = await self.require_role(organization_id, principal.user_id, OrgRole.ADMIN)
        current_raw = await self.repo.membership(organization_id, user_id)
        if current_raw is None:
            raise NotFoundError("Member not found.")
        current = Member.model_validate(current_raw)

        changes = patch.model_dump(mode="python", exclude_unset=True)
        new_role = OrgRole(changes["role"]) if changes.get("role") else None

        if new_role == OrgRole.OWNER and actor.role != OrgRole.OWNER:
            raise PermissionDeniedError("Only an owner can grant the owner role.")
        if new_role is not None and new_role != current.role and current.role == OrgRole.OWNER:
            raise PermissionDeniedError("The organization owner cannot be demoted.")
        if current.role == OrgRole.OWNER and actor.role != OrgRole.OWNER:
            raise PermissionDeniedError("Only an owner can change the owner's membership.")

        team_ids = changes.get("team_ids")
        updated = current.model_copy(update=changes)
        await self.repo.save_membership(
            organization_id, user_id, updated.model_dump(mode="python")
        )

        if team_ids is not None:
            for team_id in set(current.team_ids) - set(team_ids):
                await self._remove_from_team(organization_id, team_id, user_id)
            for team_id in set(team_ids) - set(current.team_ids):
                await self._add_to_team(organization_id, team_id, user_id)

        if new_role is not None and new_role != current.role:
            await self.audit.record(
                organization_id,
                AuditAction.MEMBER_ROLE_CHANGED,
                actor_id=principal.user_id,
                actor_name=principal.display_name,
                summary=f"{principal.display_name} changed a member role from "
                f"{current.role.value} to {new_role.value}",
                target_type="member",
                target_id=user_id,
                metadata={
                    "from": current.role.value,
                    "to": new_role.value,
                    "team_ids": list(updated.team_ids),
                },
            )
        return await self._member_with_user(updated.model_dump(mode="python"))

    async def remove_member(
        self, principal: Principal, organization_id: str, user_id: str
    ) -> None:
        actor = await self.require_role(organization_id, principal.user_id, OrgRole.ADMIN)
        raw = await self.repo.membership(organization_id, user_id)
        if raw is None:
            raise NotFoundError("Member not found.")
        member = Member.model_validate(raw)
        if member.role == OrgRole.OWNER:
            raise PermissionDeniedError("The organization owner cannot be removed.")
        if actor.role != OrgRole.OWNER and ROLE_RANK.get(member.role, 0) > ROLE_RANK[OrgRole.ADMIN]:
            raise PermissionDeniedError("Only an owner can remove another owner.")

        await self.repo.delete(Paths.members(organization_id), user_id)
        for team_id in member.team_ids:
            await self._remove_from_team(organization_id, team_id, user_id)
        await self.audit.record(
            organization_id,
            AuditAction.MEMBER_REMOVED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} removed a member from the organization",
            target_type="member",
            target_id=user_id,
            metadata={"role": member.role.value},
        )

    # ---- helpers ----------------------------------------------------------

    async def _member_with_user(self, raw: dict[str, Any]) -> MemberWithUser:
        member = Member.model_validate(raw)
        user_raw = await self.repo.get_user(member.user_id)
        user = User.model_validate(user_raw) if user_raw else None
        return MemberWithUser(**member.model_dump(mode="python"), user=user)

    async def _add_to_team(self, organization_id: str, team_id: str, user_id: str) -> None:
        raw = await self.repo.get(Paths.teams(organization_id), team_id)
        if raw is None:
            raise NotFoundError("Team not found.")
        member_ids = list(raw.get("member_ids") or [])
        if user_id not in member_ids:
            member_ids.append(user_id)
        await self.repo.patch(Paths.teams(organization_id), team_id, {"member_ids": member_ids})
        membership = await self.repo.membership(organization_id, user_id)
        if membership is None:
            return
        teams = list(membership.get("team_ids") or [])
        if team_id not in teams:
            teams.append(team_id)
        await self.repo.save_membership(organization_id, user_id, {**membership, "team_ids": teams})

    async def _remove_from_team(self, organization_id: str, team_id: str, user_id: str) -> None:
        raw = await self.repo.get(Paths.teams(organization_id), team_id)
        if raw is not None:
            member_ids = [uid for uid in list(raw.get("member_ids") or []) if uid != user_id]
            await self.repo.patch(
                Paths.teams(organization_id), team_id, {"member_ids": member_ids}
            )
        membership = await self.repo.membership(organization_id, user_id)
        if membership is None:
            return
        teams = [tid for tid in list(membership.get("team_ids") or []) if tid != team_id]
        await self.repo.save_membership(organization_id, user_id, {**membership, "team_ids": teams})
