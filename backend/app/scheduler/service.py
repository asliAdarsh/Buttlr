"""Scheduling for deployed Buttlrs.

``SchedulerService`` owns one APScheduler ``AsyncIOScheduler`` job per deployed Buttlr with
a non-manual schedule. The job id is ``buttlr:{organization_id}:{buttlr_id}`` so a job can
be re-added idempotently whenever a Buttlr is updated, paused or deployed.

A scheduled tick is a real run: the job body reloads the organization and the Buttlr from
the store, resolves an :class:`AccessContext` from the account that created the Buttlr
(falling back to the organization owner), creates a queued execution through the runner and
submits it. Scheduled runs are therefore bounded by the same semaphore and wall-clock
timeout as every other run.

Scheduling is a convenience, never a hard dependency. If APScheduler is missing or fails
to start, the app keeps running and every other trigger — manual runs, chat, approval
resumes — continues to work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import Settings
from app.core.logging import get_logger
from app.database.base import Query, Store
from app.database.repository import Paths, Repository
from app.runtime.permissions.engine import AccessContext
from app.schemas.buttlr import Buttlr, Schedule
from app.schemas.common import utcnow
from app.schemas.enums import ButtlrStatus, ExecutionTrigger, OrgRole, ScheduleKind
from app.schemas.organization import Organization
from app.services.audit import AuditService
from app.workers.runner import ExecutionJob, ExecutionRunner

logger = get_logger(__name__)

try:  # pragma: no cover - import guard
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - import guard
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]
    DateTrigger = None  # type: ignore[assignment]
    IntervalTrigger = None  # type: ignore[assignment]
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler is unavailable; scheduled runs are disabled (%s)", exc)

JOB_PREFIX = "buttlr"

# Business hours: Monday-Friday, 09:00-18:00 local time in the schedule's timezone.
BUSINESS_HOURS_START = 9
BUSINESS_HOURS_END = 18
BUSINESS_HOURS_DAYS = frozenset({0, 1, 2, 3, 4})

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class SchedulerService:
    """Maps each deployed Buttlr's schedule onto an APScheduler job."""

    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        runner: ExecutionRunner,
        audit: AuditService,
    ) -> None:
        self.settings = settings
        self.store = store
        self.runner = runner
        self.audit = audit
        self.repo = Repository(store)
        self._scheduler: Any | None = None

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Start APScheduler and sync every organization. Never raises."""
        if not APSCHEDULER_AVAILABLE:
            logger.warning("scheduler not started: APScheduler is not installed")
            return
        if self._scheduler is not None:
            return
        try:
            scheduler = AsyncIOScheduler(timezone=self.settings.scheduler_timezone)
            scheduler.start()
        except Exception:
            logger.exception("scheduler failed to start; scheduled runs are disabled")
            return
        self._scheduler = scheduler
        logger.info("scheduler started timezone=%s", self.settings.scheduler_timezone)
        await self.sync()

    async def stop(self) -> None:
        """Shut the scheduler down. Never raises."""
        scheduler, self._scheduler = self._scheduler, None
        if scheduler is None:
            return
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("scheduler failed to shut down cleanly")
            return
        logger.info("scheduler stopped")

    # ---- synchronisation --------------------------------------------------

    async def sync(self, organization_id: str | None = None) -> int:
        """Reconcile APScheduler jobs with the stored Buttlrs.

        Adds or replaces a job for every deployed Buttlr with a non-manual schedule and
        removes jobs that no longer qualify. Returns how many Buttlrs now have a job.
        """
        if organization_id is not None:
            organizations = await self._load_organizations([organization_id])
        else:
            organizations = await self._load_all_organizations()

        wanted: set[str] = set()
        scheduled = 0

        for organization in organizations:
            rows = await self.repo.list(
                Paths.buttlrs(organization.id), order_by="created_at", limit=None
            )
            for row in rows:
                buttlr = Buttlr.model_validate(row)
                job_id = self.job_id(organization.id, buttlr.id)
                if not self._should_run(buttlr):
                    self._remove_job(job_id)
                    continue
                if self._schedule(organization, buttlr):
                    wanted.add(job_id)
                    scheduled += 1

        self._remove_jobs_except(wanted)
        logger.info(
            "scheduler synced organizations=%s scheduled=%s", len(organizations), scheduled
        )
        return scheduled

    async def next_runs(self, organization_id: str) -> list[dict[str, Any]]:
        """Upcoming run time per Buttlr; ``None`` for manual or unscheduled Buttlrs."""
        rows = await self.repo.list(
            Paths.buttlrs(organization_id), order_by="created_at", limit=None
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            buttlr = Buttlr.model_validate(row)
            next_run_at: datetime | None = None
            job = self._get_job(self.job_id(organization_id, buttlr.id))
            if job is not None:
                next_run_at = getattr(job, "next_run_time", None)
            results.append(
                {"buttlr_id": buttlr.id, "name": buttlr.name, "next_run_at": next_run_at}
            )
        return results

    # ---- job body ---------------------------------------------------------

    async def _run_buttlr(self, organization_id: str, buttlr_id: str) -> None:
        """One scheduled tick. Never raises — a failed tick is logged, not propagated."""
        try:
            organization = await self._load_organization(organization_id)
            if organization is None:
                logger.warning("skipping run: organization %s is gone", organization_id)
                return
            row = await self.repo.get(Paths.buttlrs(organization_id), buttlr_id)
            if row is None:
                logger.info("skipping run: Buttlr %s is gone", buttlr_id)
                return
            buttlr = Buttlr.model_validate(row)

            if not self._should_run(buttlr):
                logger.debug("skipping run for %s: no longer scheduled", buttlr_id)
                return
            if buttlr.schedule.business_hours_only and not self._within_business_hours(
                buttlr.schedule
            ):
                logger.info(
                    "skipping scheduled run for %s: outside business hours in %s",
                    buttlr.name,
                    buttlr.schedule.timezone,
                )
                return

            access = await self._access_for(organization, buttlr)
            goal = self._goal_for(buttlr)
            execution = await self.runner.create_execution(
                organization,
                buttlr,
                ExecutionTrigger.SCHEDULE,
                goal,
                access.user_id,
            )
            self.runner.submit(
                ExecutionJob(
                    organization=organization,
                    buttlr=buttlr,
                    execution=execution,
                    goal=goal,
                    trigger=ExecutionTrigger.SCHEDULE,
                    requested_by=access.user_id,
                    access=access,
                )
            )
            logger.info("scheduled run started execution=%s buttlr=%s", execution.id, buttlr.name)
        except Exception:
            logger.exception("scheduled run failed for Buttlr %s", buttlr_id)

    def _goal_for(self, buttlr: Buttlr) -> str:
        objective = buttlr.objective.strip()
        if objective:
            return objective
        return f"Carry out {buttlr.role}'s standing responsibilities."

    async def _access_for(self, organization: Organization, buttlr: Buttlr) -> AccessContext:
        """Acting account: the Buttlr's creator, else the organization owner."""
        for user_id in (buttlr.created_by, organization.owner_id):
            if not user_id:
                continue
            membership = await self.repo.get(Paths.members(organization.id), user_id)
            if membership is None:
                continue
            try:
                role = OrgRole(str(membership.get("role") or OrgRole.MEMBER.value))
            except ValueError:
                role = OrgRole.MEMBER
            return AccessContext(
                user_id=user_id,
                org_role=role,
                team_ids=tuple(membership.get("team_ids") or ()),
                settings=organization.settings,
            )
        # No membership document at all: act as the owner with no role. The permission
        # engine attenuates that to no access rather than granting everything.
        logger.warning(
            "no membership found for Buttlr %s; acting as owner without a role", buttlr.id
        )
        return AccessContext(user_id=organization.owner_id, settings=organization.settings)

    # ---- scheduling helpers -----------------------------------------------

    @staticmethod
    def job_id(organization_id: str, buttlr_id: str) -> str:
        return f"{JOB_PREFIX}:{organization_id}:{buttlr_id}"

    @staticmethod
    def _should_run(buttlr: Buttlr) -> bool:
        schedule = buttlr.schedule
        return (
            buttlr.status == ButtlrStatus.ACTIVE
            and schedule.enabled
            and schedule.kind != ScheduleKind.MANUAL
        )

    def _schedule(self, organization: Organization, buttlr: Buttlr) -> bool:
        """Add or replace this Buttlr's job. Returns False when it cannot be scheduled."""
        job_id = self.job_id(organization.id, buttlr.id)
        if self._scheduler is None:
            logger.warning("scheduler is not running; job %s was not registered", job_id)
            return False

        trigger = self.build_trigger(buttlr.schedule)
        if trigger is None:
            self._remove_job(job_id)
            return False

        try:
            self._scheduler.add_job(
                self._run_buttlr,
                trigger=trigger,
                id=job_id,
                args=[organization.id, buttlr.id],
                replace_existing=True,
                misfire_grace_time=max(60, int(self.settings.execution_timeout_seconds)),
                coalesce=True,
                max_instances=1,
            )
        except Exception:
            logger.exception("could not schedule Buttlr %s", buttlr.name)
            return False
        return True

    def build_trigger(self, schedule: Schedule) -> Any:
        """Translate a stored schedule into an APScheduler trigger, ``None`` if invalid."""
        timezone = self._timezone(schedule.timezone)
        try:
            if schedule.kind == ScheduleKind.ONCE:
                return DateTrigger(run_date=schedule.run_at or utcnow(), timezone=timezone)

            if schedule.kind == ScheduleKind.INTERVAL:
                return IntervalTrigger(minutes=schedule.interval_minutes or 60, timezone=timezone)

            if schedule.kind == ScheduleKind.HOURLY:
                return IntervalTrigger(hours=1, timezone=timezone)

            if schedule.kind == ScheduleKind.DAILY:
                hour, minute = self._hour_minute(schedule.at)
                return CronTrigger(hour=hour, minute=minute, timezone=timezone)

            if schedule.kind == ScheduleKind.WEEKLY:
                hour, minute = self._hour_minute(schedule.at)
                return CronTrigger(
                    hour=hour,
                    minute=minute,
                    day_of_week=self._day_of_week(schedule.day_of_week),
                    timezone=timezone,
                )

            if schedule.kind == ScheduleKind.MONTHLY:
                hour, minute = self._hour_minute(schedule.at)
                return CronTrigger(
                    hour=hour, minute=minute, day=schedule.day_of_month or 1, timezone=timezone
                )

            if schedule.kind == ScheduleKind.CRON:
                expression = (schedule.cron or "").strip()
                if not expression:
                    logger.warning("skipping cron schedule with no expression")
                    return None
                return CronTrigger.from_crontab(expression, timezone=timezone)
        except Exception as exc:
            logger.warning(
                "skipping %s schedule (%s): %s", schedule.kind.value, schedule.cron, exc
            )
            return None

        logger.warning("skipping unsupported schedule kind %s", schedule.kind)
        return None

    @staticmethod
    def _hour_minute(at: str | None) -> tuple[int, int]:
        if not at or ":" not in at:
            return 9, 0
        hour, _, minute = at.partition(":")
        try:
            parsed = (int(hour), int(minute))
        except ValueError:
            return 9, 0
        if not (0 <= parsed[0] <= 23 and 0 <= parsed[1] <= 59):
            return 9, 0
        return parsed

    @staticmethod
    def _day_of_week(value: str | None) -> str:
        if not value:
            return "mon"
        candidate = value.strip().lower()[:3]
        return candidate if candidate in _WEEKDAYS else "mon"

    @staticmethod
    def _timezone(name: str) -> Any:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            logger.warning("unknown timezone %r; falling back to UTC", name)
            return ZoneInfo("UTC")

    @classmethod
    def _within_business_hours(cls, schedule: Schedule) -> bool:
        local = datetime.now(cls._timezone(schedule.timezone))
        if local.weekday() not in BUSINESS_HOURS_DAYS:
            return False
        return BUSINESS_HOURS_START <= local.hour < BUSINESS_HOURS_END

    # ---- store helpers ----------------------------------------------------

    async def _load_organization(self, organization_id: str) -> Organization | None:
        row = await self.repo.get(Paths.ORGANIZATIONS, organization_id)
        return Organization.model_validate(row) if row else None

    async def _load_all_organizations(self) -> list[Organization]:
        rows = await self.store.query(Paths.ORGANIZATIONS, Query(order_by="created_at"))
        return [Organization.model_validate(row) for row in rows]

    async def _load_organizations(self, organization_ids: list[str]) -> list[Organization]:
        organizations: list[Organization] = []
        for organization_id in organization_ids:
            organization = await self._load_organization(organization_id)
            if organization is not None:
                organizations.append(organization)
        return organizations

    # ---- apscheduler helpers ----------------------------------------------

    def _get_job(self, job_id: str) -> Any:
        if self._scheduler is None:
            return None
        try:
            return self._scheduler.get_job(job_id)
        except Exception:
            logger.exception("could not read job %s", job_id)
            return None

    def _remove_job(self, job_id: str) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            logger.debug("could not remove job %s", job_id, exc_info=True)

    def _remove_jobs_except(self, wanted: set[str]) -> None:
        if self._scheduler is None:
            return
        try:
            for job in self._scheduler.get_jobs():
                job_id = str(job.id)
                if job_id.startswith(f"{JOB_PREFIX}:") and job_id not in wanted:
                    self._scheduler.remove_job(job_id)
        except Exception:
            logger.exception("could not prune stale scheduler jobs")
