"""Health and runtime metadata for the UI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ContainerDep
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(container: ContainerDep) -> dict[str, object]:
    return {
        "status": "ok",
        "name": settings.app_name,
        "version": settings.version,
        "store": container.store.backend,
        "store_healthy": await container.store.health(),
        "scheduler": settings.scheduler_enabled,
        "running_executions": container.runner.active_count(),
    }


class MetaConfig(BaseModel):
    app_name: str
    version: str
    environment: str
    auth_mode: str
    dev_login_enabled: bool
    store_backend: str
    scheduler_enabled: bool
    providers: list[str]
    github_oauth_enabled: bool
    google_oauth_enabled: bool
    demo_seed_enabled: bool
    default_timezone: str


@router.get("/meta/config", response_model=MetaConfig)
async def meta_config(container: ContainerDep) -> MetaConfig:
    try:
        providers = await container.models.available_providers()
    except Exception:
        providers = ["heuristic"]
    return MetaConfig(
        app_name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        auth_mode=settings.auth_mode,
        dev_login_enabled=settings.auth_mode == "dev",
        store_backend=container.store.backend,
        scheduler_enabled=settings.scheduler_enabled,
        providers=providers,
        github_oauth_enabled=bool(
            settings.github_oauth_client_id and settings.github_oauth_client_secret
        ),
        google_oauth_enabled=bool(
            settings.google_oauth_client_id and settings.google_oauth_client_secret
        ),
        demo_seed_enabled=settings.auth_mode == "dev",
        default_timezone=settings.scheduler_timezone,
    )
