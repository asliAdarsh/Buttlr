"""Buttlr routes: configuration, natural-language builder, run and chat."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import ContainerDep, OrgDep
from app.schemas.activity import ChatMessage, ChatRequest, ChatResponse, Conversation
from app.schemas.buttlr import (
    Buttlr,
    ButtlrCreate,
    ButtlrDraftRequest,
    ButtlrDraftResponse,
    ButtlrRefineRequest,
    ButtlrRunRequest,
    ButtlrStatus,
    ButtlrUpdate,
)
from app.schemas.execution import Execution

router = APIRouter(tags=["buttlrs"])


@router.get("/organizations/{organization_id}/buttlrs", response_model=list[Buttlr])
async def list_buttlrs(
    container: ContainerDep,
    ctx: OrgDep,
    team_id: str | None = Query(default=None),
    status_filter: ButtlrStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
) -> list[Buttlr]:
    return await container.buttlrs.list(
        ctx.organization.id, team_id=team_id, status=status_filter, q=q, access=ctx.access
    )


@router.post(
    "/organizations/{organization_id}/buttlrs",
    response_model=Buttlr,
    status_code=status.HTTP_201_CREATED,
)
async def create_buttlr(
    container: ContainerDep, ctx: OrgDep, payload: ButtlrCreate
) -> Buttlr:
    return await container.buttlrs.create(ctx.principal, ctx.organization.id, payload)


@router.post(
    "/organizations/{organization_id}/buttlrs/draft", response_model=ButtlrDraftResponse
)
async def draft_buttlr(
    container: ContainerDep, ctx: OrgDep, payload: ButtlrDraftRequest
) -> ButtlrDraftResponse:
    return await container.buttlrs.draft(ctx.principal, ctx.organization.id, payload)


@router.post(
    "/organizations/{organization_id}/buttlrs/refine", response_model=ButtlrDraftResponse
)
async def refine_buttlr(
    container: ContainerDep, ctx: OrgDep, payload: ButtlrRefineRequest
) -> ButtlrDraftResponse:
    return await container.buttlrs.refine(ctx.principal, ctx.organization.id, payload)


@router.get("/organizations/{organization_id}/buttlrs/{buttlr_id}", response_model=Buttlr)
async def get_buttlr(container: ContainerDep, ctx: OrgDep, buttlr_id: str) -> Buttlr:
    return await container.buttlrs.get(ctx.organization.id, buttlr_id, access=ctx.access)


@router.patch("/organizations/{organization_id}/buttlrs/{buttlr_id}", response_model=Buttlr)
async def update_buttlr(
    container: ContainerDep, ctx: OrgDep, buttlr_id: str, patch: ButtlrUpdate
) -> Buttlr:
    return await container.buttlrs.update(ctx.principal, ctx.organization.id, buttlr_id, patch)


@router.delete(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_buttlr(container: ContainerDep, ctx: OrgDep, buttlr_id: str) -> None:
    await container.buttlrs.delete(ctx.principal, ctx.organization.id, buttlr_id)


@router.post(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/deploy", response_model=Buttlr
)
async def deploy_buttlr(container: ContainerDep, ctx: OrgDep, buttlr_id: str) -> Buttlr:
    return await container.buttlrs.deploy(ctx.principal, ctx.organization.id, buttlr_id)


@router.post(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/pause", response_model=Buttlr
)
async def pause_buttlr(container: ContainerDep, ctx: OrgDep, buttlr_id: str) -> Buttlr:
    return await container.buttlrs.pause(ctx.principal, ctx.organization.id, buttlr_id)


@router.post(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/run", response_model=Execution
)
async def run_buttlr(
    container: ContainerDep, ctx: OrgDep, buttlr_id: str, payload: ButtlrRunRequest
) -> Execution:
    return await container.buttlrs.run(ctx.principal, ctx.organization.id, buttlr_id, payload)


@router.post(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/chat", response_model=ChatResponse
)
async def chat_with_buttlr(
    container: ContainerDep, ctx: OrgDep, buttlr_id: str, payload: ChatRequest
) -> ChatResponse:
    buttlr = await container.buttlrs.get(ctx.organization.id, buttlr_id, access=ctx.access)
    return await container.chat.send(
        principal=ctx.principal,
        organization=ctx.organization,
        buttlr=buttlr,
        message=payload.message,
        conversation_id=payload.conversation_id,
        dry_run=payload.dry_run,
    )


@router.get(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/conversations",
    response_model=list[Conversation],
)
async def list_conversations(
    container: ContainerDep, ctx: OrgDep, buttlr_id: str
) -> list[Conversation]:
    await container.buttlrs.get(ctx.organization.id, buttlr_id, access=ctx.access)
    return await container.chat.conversations(ctx.organization.id, buttlr_id)


@router.get(
    "/organizations/{organization_id}/buttlrs/{buttlr_id}/conversations/{conversation_id}/messages",
    response_model=list[ChatMessage],
)
async def list_messages(
    container: ContainerDep, ctx: OrgDep, buttlr_id: str, conversation_id: str
) -> list[ChatMessage]:
    await container.buttlrs.get(ctx.organization.id, buttlr_id, access=ctx.access)
    return await container.chat.messages(ctx.organization.id, buttlr_id, conversation_id)
