"""Authentication, session and profile routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ContainerDep, PrincipalDep
from app.auth.provider import DevTokenVerifier
from app.core.errors import UnauthenticatedError
from app.schemas.auth import DevLoginRequest, SessionContext, TokenResponse
from app.schemas.organization import User, UserUpdate

router = APIRouter(tags=["auth"])


@router.post("/auth/dev/login", response_model=TokenResponse)
async def dev_login(container: ContainerDep, payload: DevLoginRequest) -> TokenResponse:
    if not isinstance(container.verifier, DevTokenVerifier):
        raise UnauthenticatedError(
            "Development sign-in is disabled here. Sign in with your organization account."
        )
    return await container.auth.dev_login(payload.email, payload.display_name)


@router.get("/auth/session", response_model=SessionContext)
async def session(container: ContainerDep, principal: PrincipalDep) -> SessionContext:
    return await container.auth.session(principal)


@router.get("/users/me", response_model=User)
async def me(container: ContainerDep, principal: PrincipalDep) -> User:
    return await container.auth.get_user(principal.user_id)


@router.patch("/users/me", response_model=User)
async def update_me(
    container: ContainerDep, principal: PrincipalDep, patch: UserUpdate
) -> User:
    return await container.auth.update_user(principal.user_id, patch)
