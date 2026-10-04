"""Teams within an organization.

Membership is stored twice by design: ``member_ids`` on the team document (the authoritative
order used by the team view) and ``team_ids`` on each member document (so member listings can
render badges without a second query). Writes keep both in step.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.database.base import Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.schemas.auth import Principal
from app.schemas.common import utcnow
from app.schemas.enums import AuditAction, OrgRole
from app.schemas.organization import Member, MemberWithUser, Team, TeamCreate, TeamUpdate, User
from app.services.audit import AuditService

logger = get_logger(__name__)

MANAGE_ROLES = (OrgRole.OWNER, OrgRole.ADMIN)


class TeamService:
    def __init__(self, store: Store, audit: AuditService) -> None:
        self.store = store
        self.repo = Repository(store)
        self.audit = audit

    async def create(
        self, principal: Principal, organization_id: str, payload: TeamCreate
    ) -> Team:
        member = await self._require_member(organization_id, principal.user_id)
        self._require_manager(member)
        team = Team(
            id=new_id(),
            organization_id=organization_id,
            name=payload.name,
            description=payload.description,
            emoji=payload.emoji,
            color=payload.color,
            created_by=principal.user_id,
        )
        await self._save(team, payload.member_ids)
        for user_id in payload.member_ids:
            await self._add_team_to_member(organization_id, user_id, team.id)
        await self.audit.record(
            organization_id,
            AuditAction.TEAM_CREATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} created the team {team.name}",
            target_type="team",
            target_id=team.id,
            metadata={"member_ids": list(payload.member_ids)},
        )
        return team

    async def list(self, organization_id: str) -> list[Team]:
        rows = await self.repo.list(
            Paths.teams(organization_id), order_by="created_at", sort=Sort.ASC
        )
        return [Team.model_validate(row) for row in rows]

    async def get(self, organization_id: str, team_id: str) -> Team:
        raw = await self.repo.get(Paths.teams(organization_id), team_id)
        if raw is None:
            raise NotFoundError("Team not found.")
        return Team.model_validate(raw)

    async def update(
        self,
        principal: Principal,
        organization_id: str,
        team_id: str,
        patch: TeamUpdate,
    ) -> Team:
        member = await self._require_member(organization_id, principal.user_id)
        await self._require_writable(member, team_id)
        current = await self.get(organization_id, team_id)
        current_raw = await self.repo.get(Paths.teams(organization_id), team_id) or {}
        previous_ids = list(current_raw.get("member_ids") or [])

        changes = patch.model_dump(mode="python", exclude_unset=True)
        member_ids = changes.pop("member_ids", None)
        updated = current.model_copy(update=changes)
        updated.updated_at = utcnow()
        await self._save(updated, member_ids)

        if member_ids is not None:
            for user_id in set(previous_ids) - set(member_ids):
                await self._remove_team_from_member(organization_id, user_id, team_id)
            for user_id in set(member_ids) - set(previous_ids):
                await self._add_team_to_member(organization_id, user_id, team_id)

        await self.audit.record(
            organization_id,
            AuditAction.TEAM_UPDATED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} updated the team {updated.name}",
            target_type="team",
            target_id=team_id,
            metadata={"fields": sorted(changes.keys())},
        )
        return updated

    async def delete(self, principal: Principal, organization_id: str, team_id: str) -> None:
        member = await self._require_member(organization_id, principal.user_id)
        await self._require_writable(member, team_id)
        team = await self.get(organization_id, team_id)
        raw = await self.repo.get(Paths.teams(organization_id), team_id) or {}
        for user_id in list(raw.get("member_ids") or []):
            await self._remove_team_from_member(organization_id, user_id, team_id)
        await self.repo.delete(Paths.teams(organization_id), team_id)
        await self.audit.record(
            organization_id,
            AuditAction.TEAM_DELETED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{principal.display_name} deleted the team {team.name}",
            target_type="team",
            target_id=team_id,
        )

    async def members(self, organization_id: str, team_id: str) -> list[MemberWithUser]:
        raw = await self.repo.get(Paths.teams(organization_id), team_id)
        if raw is None:
            raise NotFoundError("Team not found.")
        results: list[MemberWithUser] = []
        for user_id in list(raw.get("member_ids") or []):
            membership = await self.repo.membership(organization_id, user_id)
            if membership is None:
                continue
            user_raw = await self.repo.get_user(user_id)
            results.append(
                MemberWithUser(
                    **Member.model_validate(membership).model_dump(mode="python"),
                    user=User.model_validate(user_raw) if user_raw else None,
                )
            )
        return results

    # ---- helpers ----------------------------------------------------------

    async def _require_member(self, organization_id: str, user_id: str) -> Member:
        raw = await self.repo.membership(organization_id, user_id)
        if raw is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        return Member.model_validate(raw)

    @staticmethod
    def _require_manager(member: Member) -> None:
        if member.role not in MANAGE_ROLES:
            raise PermissionDeniedError("You do not have permission to perform this action.")

    async def _require_writable(self, member: Member, team_id: str) -> None:
        if member.role in MANAGE_ROLES:
            return
        if team_id in member.team_ids:
            return
        raise PermissionDeniedError("You do not have permission to perform this action.")

    async def _save(self, team: Team, member_ids: list[str] | None) -> dict[str, Any]:
        collection = Paths.teams(team.organization_id)
        if member_ids is not None:
            unique: list[str] = []
            for user_id in member_ids:
                if user_id not in unique:
                    unique.append(user_id)
            for user_id in unique:
                if await self.repo.membership(team.organization_id, user_id) is None:
                    raise ConflictError("One or more selected people are not organization members.")
            payload = {**team.model_dump(mode="python"), "member_ids": unique}
        else:
            existing = await self.repo.get(collection, team.id) or {}
            payload = {
                **team.model_dump(mode="python"),
                "member_ids": list(existing.get("member_ids") or []),
            }
        return await self.repo.save(collection, payload)

    async def _add_team_to_member(
        self, organization_id: str, user_id: str, team_id: str
    ) -> None:
        membership = await self.repo.membership(organization_id, user_id)
        if membership is None:
            return
        team_ids = list(membership.get("team_ids") or [])
        if team_id not in team_ids:
            team_ids.append(team_id)
        await self.repo.save_membership(organization_id, user_id, {**membership, "team_ids": team_ids})

    async def _remove_team_from_member(
        self, organization_id: str, user_id: str, team_id: str
    ) -> None:
        membership = await self.repo.membership(organization_id, user_id)
        if membership is None:
            return
        team_ids = [tid for tid in list(membership.get("team_ids") or []) if tid != team_id]
        await self.repo.save_membership(organization_id, user_id, {**membership, "team_ids": team_ids})