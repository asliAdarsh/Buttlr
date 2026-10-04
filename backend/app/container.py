"""Application container.

One place where every singleton is constructed and wired. Services take their collaborators
as constructor arguments, so they stay testable and nothing reaches for a global.
"""

from __future__ import annotations

from app.auth.provider import TokenVerifier, build_verifier
from app.auth.service import AuthService
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.logging import get_logger
from app.database.base import Store
from app.database.factory import build_store
from app.database.repository import Repository
from app.integrations.service import IntegrationService
from app.runtime.executor import ButtlrExecutor
from app.runtime.models.providers import build_providers
from app.runtime.models.router import ModelRouter
from app.runtime.permissions.engine import engine as permission_engine
from app.runtime.pubsub import ExecutionBus
from app.runtime.pubsub import bus as default_bus
from app.runtime.tools import build_registry
from app.scheduler.service import SchedulerService
from app.services.analytics import AnalyticsService
from app.services.approvals import ApprovalService
from app.services.audit import AuditService
from app.services.buttlrs import ButtlrService
from app.services.chat import ChatService
from app.services.executions import ExecutionService
from app.services.notifications import NotificationService
from app.services.organizations import OrganizationService
from app.services.teams import TeamService
from app.workers.runner import ExecutionRunner

logger = get_logger(__name__)


class Container:
    def __init__(
        self,
        settings: Settings | None = None,
        store: Store | None = None,
        bus: ExecutionBus | None = None,
        verifier: TokenVerifier | None = None,
    ) -> None:
        self.settings = settings or default_settings
        self.store: Store = store or build_store(self.settings)
        self.repo = Repository(self.store)
        self.bus = bus or default_bus
        self.verifier = verifier or build_verifier(self.settings)

        # core
        self.audit = AuditService(self.store)
        self.notifications = NotificationService(self.store)
        self.auth = AuthService(self.store, self.verifier, self.settings)

        # runtime
        self.registry = build_registry()
        self.models = ModelRouter(build_providers(self.settings))
        self.permissions = permission_engine

        # domain
        self.organizations = OrganizationService(self.store, self.audit)
        self.teams = TeamService(self.store, self.audit)
        self.integrations = IntegrationService(self.store, self.audit, self.settings)
        self.approvals = ApprovalService(self.store, self.audit, self.notifications)
        self.executions = ExecutionService(self.store, self.audit, self.bus)

        # runtime orchestration
        self.executor = ButtlrExecutor(
            settings=self.settings,
            store=self.store,
            registry=self.registry,
            models=self.models,
            permissions=self.permissions,
            executions=self.executions,
            approvals=self.approvals,
            integrations=self.integrations,
            audit=self.audit,
            notifications=self.notifications,
            bus=self.bus,
        )
        self.runner = ExecutionRunner(self.executor, self.settings)

        self.buttlrs = ButtlrService(
            store=self.store,
            audit=self.audit,
            registry=self.registry,
            models=self.models,
            runner=self.runner,
            bus=self.bus,
            settings=self.settings,
        )
        self.analytics = AnalyticsService(self.store)
        self.chat = ChatService(
            store=self.store,
            runner=self.runner,
            executions=self.executions,
            buttlrs=self.buttlrs,
            settings=self.settings,
            audit=self.audit,
        )

        # scheduling
        self.scheduler = SchedulerService(
            settings=self.settings,
            store=self.store,
            runner=self.runner,
            audit=self.audit,
        )

    async def startup(self) -> None:
        await self.runner.start()
        if self.settings.scheduler_enabled:
            await self.scheduler.start()
        logger.info(
            "buttlr ready store=%s auth=%s providers=%s",
            self.store.backend,
            self.settings.auth_mode,
            ",".join(self.models.providers.keys()),
        )

    async def shutdown(self) -> None:
        await self.scheduler.stop()
        await self.runner.stop()
        for provider in self.models.providers.values():
            await provider.close()
        await self.store.close()


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container | None) -> None:
    global _container
    _container = container
