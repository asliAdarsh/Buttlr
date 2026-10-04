"""Authentication service: token → user → session."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.auth.provider import DevTokenVerifier, TokenVerifier, VerifiedIdentity
from app.core.config import Settings
from app.core.errors import NotFoundError, UnauthenticatedError
from app.core.logging import get_logger
from app.database.base import Store, eq
from app.database.repository import Paths, Repository
from app.schemas.auth import Principal, SessionContext, TokenResponse
from app.schemas.common import utcnow
from app.schemas.enums import OrgRole
from app.schemas.organization import Organization, User, UserPreferences, UserUpdate

logger = get_logger(__name__)


class AuthService:
    def __init__(self, store: Store, verifier: TokenVerifier, settings: Settings) -> None:
        self.repo = Repository(store)
        self.verifier = verifier
        self.settings = settings

    # ---- tokens -----------------------------------------------------------

    async def principal_from_token(self, token: str) -> Principal:
        identity = await self.verifier.verify(token)
        user, memberships = await self._ensure_user(identity)
        organization_id = user.default_organization_id
        if organization_id and not any(m["organization_id"] == organization_id for m in memberships):
            organization_id = None
        if organization_id is None and memberships:
            organization_id = memberships[0]["organization_id"]
            await self.repo.patch(Paths.USERS, user.id, {"default_organization_id": organization_id})
            user.default_organization_id = organization_id

        active = next(
            (m for m in memberships if m["organization_id"] == organization_id), None
        )
        return Principal(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            photo_url=user.photo_url,
            organization_id=organization_id,
            role=OrgRole(active["role"]) if active else None,
            team_ids=list(active.get("team_ids") or []) if active else [],
            is_dev=self.verifier.mode == "dev",
        )

    # ---- user provisioning ------------------------------------------------

    async def _ensure_user(self, identity: VerifiedIdentity) -> tuple[User, list[dict]]:
        raw = await self.repo.get_user(identity.user_id)
        if raw is None:
            user = User(
                id=identity.user_id,
                email=identity.email,
                display_name=identity.display_name,
                photo_url=identity.photo_url,
            )
            await self.repo.upsert_user(user.id, user.model_dump(mode="python"))
            logger.info("provisioned user %s", user.id)
        else:
            user = User.model_validate(raw)
            changes: dict[str, object] = {"last_seen_at": utcnow()}
            if identity.display_name and identity.display_name != user.display_name:
                changes["display_name"] = identity.display_name
                user.display_name = identity.display_name
            if identity.photo_url and identity.photo_url != user.photo_url:
                changes["photo_url"] = identity.photo_url
                user.photo_url = identity.photo_url
            await self.repo.patch(Paths.USERS, user.id, changes)
        memberships = await self.repo.memberships_for_user(user.id)
        return user, memberships

    async def dev_login(self, email: str, display_name: str | None = None) -> TokenResponse:
        if not isinstance(self.verifier, DevTokenVerifier):
            raise UnauthenticatedError("Development login is disabled in this environment.")

        email = email.strip().lower()
        existing = await self.repo.store.query_one(Paths.USERS, [eq("email", email)])
        name = display_name or email.split("@")[0].replace(".", " ").title()
        if existing:
            user_id = existing["id"]
            await self.repo.patch(Paths.USERS, user_id, {"last_seen_at": utcnow()})
        else:
            user_id = f"{email.split('@')[0][:20]}-{uuid.uuid4().hex[:6]}"
            await self.repo.upsert_user(
                user_id,
                {
                    "id": user_id,
                    "email": email,
                    "display_name": name,
                    "preferences": UserPreferences().model_dump(mode="python"),
                    "created_at": utcnow(),
                    "updated_at": utcnow(),
                    "last_seen_at": utcnow(),
                },
            )

        token, ttl = self.verifier.issue(user_id, email, name)
        user = await self.get_user(user_id)
        return TokenResponse(access_token=token, expires_in=ttl, user=user)

    # ---- reads ------------------------------------------------------------

    async def get_user(self, user_id: str) -> User:
        raw = await self.repo.get_user(user_id)
        if raw is None:
            raise NotFoundError("User not found.")
        return User.model_validate(raw)

    async def update_user(self, user_id: str, patch: UserUpdate) -> User:
        changes = patch.model_dump(exclude_unset=True, mode="python")
        if not changes:
            return await self.get_user(user_id)
        changes["updated_at"] = utcnow()
        raw = await self.repo.patch(Paths.USERS, user_id, _flatten(changes))
        return User.model_validate(raw)

    async def session(self, principal: Principal) -> SessionContext:
        user = await self.get_user(principal.user_id)
        memberships = await self.repo.memberships_for_user(principal.user_id)
        organizations: list[Organization] = []
        for membership in sorted(memberships, key=lambda m: m.get("joined_at") or datetime.min):
            raw = await self.repo.get(Paths.ORGANIZATIONS, membership["organization_id"])
            if raw:
                organizations.append(Organization.model_validate(raw))
        return SessionContext(
            user=user,
            organizations=organizations,
            active_organization_id=principal.organization_id,
        )

    async def ensure_organization_membership(
        self, organization_id: str, user_id: str, role: OrgRole, team_ids: list[str] | None = None
    ) -> None:
        await self.repo.save_membership(
            organization_id,
            user_id,
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "role": role.value,
                "team_ids": team_ids or [],
                "joined_at": utcnow(),
            },
        )


def _flatten(changes: dict) -> dict:
    """Preferences are stored as a nested map; keep them intact but drop unset keys."""
    out: dict = {}
    for key, value in changes.items():
        if hasattr(value, "model_dump"):
            out[key] = value.model_dump(mode="python")
        else:
            out[key] = value
    return out
