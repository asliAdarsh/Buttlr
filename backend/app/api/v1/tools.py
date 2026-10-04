"""Tool catalogue."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ContainerDep, PrincipalDep

router = APIRouter(tags=["tools"])


@router.get("/tools")
async def list_tools(container: ContainerDep, principal: PrincipalDep) -> dict[str, Any]:
    catalogue = container.registry.catalogue()
    integrations = sorted({tool["integration"] for tool in catalogue if tool.get("integration")})
    return {"tools": catalogue, "integrations": integrations, "total": len(catalogue)}
