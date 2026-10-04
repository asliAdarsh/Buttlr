"""Bounded background execution of Buttlr runs.

``ExecutionRunner`` is the only place a run becomes an asyncio task. Requests, scheduled
ticks, chat messages and approval decisions all hand a job to
:meth:`ExecutionRunner.submit` / :meth:`ExecutionRunner.submit_resume` and return
immediately.

Two invariants hold everywhere in this module:

* ``submit``/``submit_resume`` never raise into the caller — a submission failure is logged
  and swallowed, because the caller is usually an HTTP handler or an APScheduler tick.
* every run is bounded twice: by a semaphore (``settings.execution_workers``) so concurrency
  is capped, and by ``asyncio.wait_for(..., settings.execution_timeout_seconds)`` so a
  Buttlr that stalls cannot hold a worker slot forever. A timeout marks the execution
  failed.

The job payloads themselves (``ExecutionJob``, ``ResumeJob``) are defined by the executor in
``app.runtime.executor`` and re-exported here for the call sites that build them.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.runtime.executor import ButtlrExecutor, ExecutionJob, ResumeJob
from app.schemas.buttlr import Buttlr
from app.schemas.enums import ExecutionStatus, ExecutionTrigger
from app.schemas.execution import Execution
from app.schemas.organization import Organization

logger = get_logger(__name__)

__all__ = ["ExecutionJob", "ExecutionRunner", "ResumeJob"]


class ExecutionRunner:
    """Fire-and-forget dispatcher with bounded concurrency."""

    def __init__(self, executor: ButtlrExecutor, settings: Settings) -> None:
        self.executor = executor
        self.settings = settings
        self._semaphore = asyncio.Semaphore(max(1, settings.execution_workers))
        self._tasks: set[asyncio.Task[Any]] = set()

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        """Drop tasks left over from a previous loop. Safe to call more than once."""
        self._prune()
        logger.info("execution runner ready workers=%s", self.settings.execution_workers)

    async def stop(self) -> None:
        """Cancel every in-flight run and wait for the cancellations to land."""
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("execution runner stopped cancelled=%s", len(tasks))

    # ---- submission -------------------------------------------------------

    def submit(self, job: ExecutionJob) -> None:
        """Schedule a run. Never raises into the caller."""
        self._spawn(job.execution.organization_id, job.execution.id, self._run_job(job))

    def submit_resume(self, job: ResumeJob) -> None:
        """Schedule a resumed run after an approval decision. Never raises into the caller."""
        self._spawn(job.execution.organization_id, job.execution.id, self._run_resume_job(job))

    async def create_execution(
        self,
        organization: Organization,
        buttlr: Buttlr,
        trigger: ExecutionTrigger,
        goal: str,
        requested_by: str | None,
        dry_run: bool = False,
        conversation_id: str | None = None,
    ) -> Execution:
        """Create a queued execution through the executor's execution service."""
        return await self.executor.executions.create(
            organization_id=organization.id,
            buttlr=buttlr,
            trigger=trigger,
            goal=goal,
            requested_by=requested_by,
            dry_run=dry_run,
            conversation_id=conversation_id,
        )

    def active_count(self) -> int:
        """Number of runs currently in flight."""
        self._prune()
        return len(self._tasks)

    # ---- internals --------------------------------------------------------

    def _spawn(self, organization_id: str, execution_id: str, coro: Any) -> None:
        """Wrap a coroutine in a tracked, bounded task. Never raises."""
        try:
            task = asyncio.create_task(self._guard(organization_id, execution_id, coro))
        except RuntimeError as exc:
            # No running loop: the caller submits before the server is serving. Close the
            # coroutine so Python does not warn, and drop the run.
            coro.close()
            logger.warning("dropped execution %s: no running event loop (%s)", execution_id, exc)
            return
        self._tasks.add(task)

    async def _guard(self, organization_id: str, execution_id: str, coro: Any) -> None:
        """Bound one run by the worker semaphore and the wall-clock timeout."""
        try:
            async with self._semaphore:
                await asyncio.wait_for(coro, timeout=self.settings.execution_timeout_seconds)
        except TimeoutError:
            logger.warning(
                "execution %s exceeded %ss and was stopped",
                execution_id,
                self.settings.execution_timeout_seconds,
            )
            await self._fail_timed_out(organization_id, execution_id)
        except asyncio.CancelledError:
            logger.info("execution %s was cancelled", execution_id)
            raise
        except Exception:
            logger.exception("execution %s failed", execution_id)

    async def _run_job(self, job: ExecutionJob) -> None:
        await self.executor.run(job)

    async def _run_resume_job(self, job: ResumeJob) -> None:
        await self.executor.resume(job)

    async def _fail_timed_out(self, organization_id: str, execution_id: str) -> None:
        try:
            execution = await self.executor.executions.get(organization_id, execution_id)
            if execution is None:
                return
            await self.executor.executions.set_status(
                execution, ExecutionStatus.FAILED, error="The Buttlr run timed out."
            )
        except Exception:
            logger.exception("could not mark execution %s as timed out", execution_id)

    def _prune(self) -> None:
        for task in [t for t in self._tasks if t.done()]:
            self._tasks.discard(task)
