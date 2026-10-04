"""Scheduling: a deployed Buttlr with a schedule gets exactly one timezone-correct job."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.container import Container
from app.schemas.buttlr import ButtlrCreate, Schedule
from app.schemas.enums import ScheduleKind
from app.schemas.organization import OrganizationCreate

IST = timezone(timedelta(hours=5, minutes=30))


async def world(container: Container, schedule: Schedule):
    tokens = await container.auth.dev_login("scheduler@example.com", "Scheduler")
    principal = await container.auth.principal_from_token(tokens.access_token)
    organization = await container.organizations.create(
        principal, OrganizationCreate(name="Schedule Corp")
    )
    principal = principal.model_copy(update={"organization_id": organization.id})
    buttlr = await container.buttlrs.create(
        principal,
        organization.id,
        ButtlrCreate(name="Morning Check", tools=[], schedule=schedule),
    )
    return principal, organization, buttlr


def daily(at: str, tz: str) -> Schedule:
    return Schedule(enabled=True, kind=ScheduleKind.DAILY, at=at, timezone=tz)


async def test_a_deployed_buttlr_is_scheduled_in_its_own_timezone(container: Container) -> None:
    principal, organization, buttlr = await world(container, daily("09:00", "Asia/Kolkata"))
    assert buttlr.status.value == "draft", "a new Buttlr is never deployed by accident"

    await container.scheduler.start()
    try:
        assert container.scheduler._scheduler.get_jobs() == [], "a draft must not be scheduled"

        deployed = await container.buttlrs.deploy(principal, organization.id, buttlr.id)
        assert deployed.status.value == "active"
        assert await container.scheduler.sync(organization.id) == 1

        runs = await container.scheduler.next_runs(organization.id)
        assert len(runs) == 1
        next_run = runs[0]["next_run_at"]
        assert isinstance(next_run, datetime)
        offset = next_run.utcoffset()
        assert offset == IST.utcoffset(next_run), "the schedule's timezone must be honoured"
        assert (next_run.hour, next_run.minute) == (9, 0)
    finally:
        await container.scheduler.stop()


async def test_pausing_removes_the_job(container: Container) -> None:
    principal, organization, buttlr = await world(container, daily("08:30", "UTC"))
    await container.buttlrs.deploy(principal, organization.id, buttlr.id)
    await container.scheduler.start()
    try:
        assert await container.scheduler.sync(organization.id) == 1
        await container.buttlrs.pause(principal, organization.id, buttlr.id)
        assert await container.scheduler.sync(organization.id) == 0
        assert container.scheduler._scheduler.get_jobs() == []
        assert (await container.scheduler.next_runs(organization.id))[0]["next_run_at"] is None
    finally:
        await container.scheduler.stop()


async def test_manual_schedules_are_never_scheduled(container: Container) -> None:
    principal, organization, buttlr = await world(
        container, Schedule(enabled=False, kind=ScheduleKind.MANUAL)
    )
    await container.buttlrs.deploy(principal, organization.id, buttlr.id)
    await container.scheduler.start()
    try:
        assert await container.scheduler.sync(organization.id) == 0
        assert container.scheduler._scheduler.get_jobs() == []
    finally:
        await container.scheduler.stop()


async def test_every_schedule_kind_maps_to_a_real_trigger(container: Container) -> None:
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = container.scheduler
    cases: list[tuple[Schedule, type]] = [
        (Schedule(enabled=True, kind=ScheduleKind.HOURLY), IntervalTrigger),
        (
            Schedule(enabled=True, kind=ScheduleKind.INTERVAL, interval_minutes=30),
            IntervalTrigger,
        ),
        (daily("09:00", "UTC"), CronTrigger),
        (
            Schedule(
                enabled=True, kind=ScheduleKind.WEEKLY, at="08:00", day_of_week="mon"
            ),
            CronTrigger,
        ),
        (
            Schedule(
                enabled=True, kind=ScheduleKind.MONTHLY, at="07:30", day_of_month=1
            ),
            CronTrigger,
        ),
        (Schedule(enabled=True, kind=ScheduleKind.CRON, cron="0 9 * * 1-5"), CronTrigger),
        (
            Schedule(
                enabled=True,
                kind=ScheduleKind.ONCE,
                run_at=datetime.now(UTC) + timedelta(hours=1),
            ),
            DateTrigger,
        ),
    ]
    for schedule, expected in cases:
        trigger = scheduler.build_trigger(schedule)
        assert isinstance(trigger, expected), f"{schedule.kind.value} -> {trigger!r}"

    assert scheduler.build_trigger(Schedule(enabled=False, kind=ScheduleKind.MANUAL)) is None
    assert scheduler.build_trigger(Schedule(enabled=True, kind=ScheduleKind.CRON, cron=None)) is None
