"""Chat with a Buttlr.

The user message is persisted immediately so the transcript is never lost, then a run is
created with trigger ``CHAT`` and submitted to the runner.

The assistant reply is **not** written here. ``ButtlrExecutor`` appends a ``ChatMessage``
with ``role=assistant`` once the run finishes, so the UI receives the real answer through
the same execution stream it already listens to. What :meth:`ChatService.send` returns is
therefore a placeholder message — built locally, never persisted — that names the Buttlr
and points at the run in progress. It carries the execution id so the client can follow
along and will later be replaced in place by the persisted reply.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.database.base import Sort, Store, new_id
from app.database.repository import Paths, Repository
from app.runtime.permissions.engine import AccessContext, engine
from app.schemas.activity import ChatMessage, ChatResponse, Conversation
from app.schemas.auth import Principal
from app.schemas.buttlr import Buttlr
from app.schemas.common import utcnow
from app.schemas.enums import AuditAction, ChatRole, ExecutionTrigger, Permission
from app.schemas.organization import Organization, OrgRole
from app.services.audit import AuditService
from app.services.buttlrs import ButtlrService
from app.services.executions import ExecutionService
from app.workers.runner import ExecutionJob, ExecutionRunner

logger = get_logger(__name__)

CONVERSATION_TITLE_MAX = 60


class ChatService:
    """Accepts a message, starts a run, returns the conversation."""

    def __init__(
        self,
        *,
        store: Store,
        runner: ExecutionRunner,
        executions: ExecutionService,
        buttlrs: ButtlrService,
        settings: Settings,
        audit: AuditService,
    ) -> None:
        self.store = store
        self.runner = runner
        self.executions = executions
        self.buttlrs = buttlrs
        self.settings = settings
        self.audit = audit
        self.repo = Repository(store)

    # ---- send -------------------------------------------------------------

    async def send(
        self,
        *,
        principal: Principal,
        organization: Organization,
        buttlr: Buttlr,
        message: str,
        conversation_id: str | None,
        dry_run: bool = False,
    ) -> ChatResponse:
        text = (message or "").strip()
        if not text:
            raise ValidationError("Write a message before sending it.")

        access = await self._access_for(principal, organization)
        engine.require(
            buttlr=buttlr,
            access=access,
            permission=Permission.ASK,
            action="send it a message",
        )

        conversation = await self._ensure_conversation(
            organization_id=organization.id,
            buttlr=buttlr,
            conversation_id=conversation_id,
            created_by=principal.user_id,
            first_message=text,
        )

        user_message = await self._append_message(
            conversation=conversation,
            buttlr_id=buttlr.id,
            role=ChatRole.USER,
            content=text,
            created_by=principal.user_id,
        )

        execution = await self.executions.create(
            organization_id=organization.id,
            buttlr=buttlr,
            trigger=ExecutionTrigger.CHAT,
            goal=text,
            requested_by=principal.user_id,
            dry_run=dry_run,
            conversation_id=conversation.id,
        )
        self.runner.submit(
            ExecutionJob(
                organization=organization,
                buttlr=buttlr,
                execution=execution,
                goal=text,
                trigger=ExecutionTrigger.CHAT,
                requested_by=principal.user_id,
                access=access,
                dry_run=dry_run,
                conversation_id=conversation.id,
            )
        )

        await self.audit.record(
            organization.id,
            AuditAction.EXECUTION_STARTED,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            summary=f"{buttlr.name} started working on a message",
            target_type="execution",
            target_id=execution.id,
            buttlr_id=buttlr.id,
        )

        # Placeholder only — the persisted reply is written by the executor when the run
        # finishes. See the module docstring.
        reply = ChatMessage(
            id=new_id(),
            organization_id=organization.id,
            buttlr_id=buttlr.id,
            conversation_id=conversation.id,
            role=ChatRole.ASSISTANT,
            content=f"{buttlr.name} is working on it — the result will appear here.",
            execution_id=execution.id,
        )
        logger.debug(
            "chat run started execution=%s conversation=%s message=%s",
            execution.id,
            conversation.id,
            user_message.id,
        )

        return ChatResponse(
            conversation_id=conversation.id,
            reply=reply,
            execution_id=execution.id,
        )

    # ---- reads ------------------------------------------------------------

    async def conversations(self, organization_id: str, buttlr_id: str) -> list[Conversation]:
        rows = await self.repo.list(
            Paths.conversations(organization_id, buttlr_id),
            order_by="updated_at",
            sort=Sort.DESC,
        )
        return [Conversation.model_validate(row) for row in rows]

    async def messages(
        self, organization_id: str, buttlr_id: str, conversation_id: str
    ) -> list[ChatMessage]:
        rows = await self.repo.list(
            Paths.messages(organization_id, buttlr_id, conversation_id),
            order_by="created_at",
            sort=Sort.ASC,
        )
        return [ChatMessage.model_validate(row) for row in rows]

    # ---- internals --------------------------------------------------------

    async def _access_for(
        self, principal: Principal, organization: Organization
    ) -> AccessContext:
        """Membership is read from the store; never from the request."""
        membership = await self.repo.get(Paths.members(organization.id), principal.user_id)
        if membership is None:
            raise PermissionDeniedError("You are not a member of this organization.")
        return AccessContext(
            user_id=principal.user_id,
            org_role=_role(membership.get("role")),
            team_ids=tuple(membership.get("team_ids") or ()),
            settings=organization.settings,
        )

    async def _ensure_conversation(
        self,
        *,
        organization_id: str,
        buttlr: Buttlr,
        conversation_id: str | None,
        created_by: str,
        first_message: str,
    ) -> Conversation:
        if conversation_id:
            row = await self.repo.get(
                Paths.conversations(organization_id, buttlr.id), conversation_id
            )
            if row is None:
                raise NotFoundError("That conversation no longer exists.")
            return Conversation.model_validate(row)

        conversation = Conversation(
            id=new_id(),
            organization_id=organization_id,
            buttlr_id=buttlr.id,
            title=_title_from(first_message, buttlr.name),
            created_by=created_by,
        )
        await self.repo.save(
            Paths.conversations(organization_id, buttlr.id), conversation.model_dump(mode="python")
        )
        return conversation

    async def _append_message(
        self,
        *,
        conversation: Conversation,
        buttlr_id: str,
        role: ChatRole,
        content: str,
        created_by: str | None,
        execution_id: str | None = None,
    ) -> ChatMessage:
        now = utcnow()
        record = ChatMessage(
            id=new_id(),
            organization_id=conversation.organization_id,
            buttlr_id=buttlr_id,
            conversation_id=conversation.id,
            role=role,
            content=content,
            execution_id=execution_id,
            created_by=created_by,
            created_at=now,
        )
        await self.repo.save(
            Paths.messages(conversation.organization_id, buttlr_id, conversation.id),
            record.model_dump(mode="python"),
        )
        await self.repo.patch(
            Paths.conversations(conversation.organization_id, buttlr_id),
            conversation.id,
            {"message_count": conversation.message_count + 1, "updated_at": now},
        )
        conversation.message_count += 1
        conversation.updated_at = now
        return record


def _title_from(message: str, fallback: str) -> str:
    collapsed = " ".join(message.split())
    if not collapsed:
        return fallback
    if len(collapsed) <= CONVERSATION_TITLE_MAX:
        return collapsed
    return collapsed[: CONVERSATION_TITLE_MAX - 1].rstrip() + "…"


def _role(value: object) -> OrgRole | None:
    try:
        return OrgRole(str(value)) if value else None
    except ValueError:
        return None
