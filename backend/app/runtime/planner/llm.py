"""Model-backed planner.

``LLMPlanner`` asks the Buttlr's configured model for the single next action. It renders the
run so far as a compact conversation — the Buttlr's own instructions as the system message,
each completed step as an assistant/user turn — then asks for exactly one tool call or one
final answer.

The model is treated as untrusted input: a call to a tool the Buttlr was not granted, or a
response that is neither a call nor an answer, is a failure. Every such failure raises
``PlannerError`` so the executor can fall back to the deterministic planner instead of
running something unverified.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.errors import ModelError
from app.core.logging import get_logger
from app.runtime.models.base import CompletionRequest, Message, ToolSpec
from app.runtime.models.router import ModelRouter
from app.runtime.planner.base import Observation, Plan, Planner, PlannerError, PlanRequest
from app.schemas.buttlr import ModelConfig
from app.schemas.enums import ModelProviderKind

logger = get_logger(__name__)

__all__ = ["LLMPlanner"]

_MAX_OBSERVATION_CHARS = 1200

_SYSTEM_SUFFIX = """
You are working through one task at a time. Decide exactly one next action:

- Call exactly one of the tools above to gather more data, or
- Answer with the final report once you have enough.

Never call a tool that is not listed. Never invent data: every fact in your final answer must
come from a tool result you have already seen. When a tool asked for approval was declined, say
so in the report instead of retrying it. Keep the final answer to a short markdown report: one
headline line, a few bullets of findings, and a closing note about anything that needed
approval or could not be completed."""


class LLMPlanner(Planner):
    """A ``Planner`` that reasons with the Buttlr's configured model."""

    id = "llm"

    def __init__(self, models: ModelRouter, config: ModelConfig) -> None:
        self._models = models
        self._config = config
        #: Why the model did not answer, for the run's activity log.
        self.last_error: str | None = None

    @property
    def config(self) -> ModelConfig:
        return self._config

    def _degraded_reason(self) -> str:
        """The first real provider's failure, if one was recorded."""
        for provider, message in self._models.last_failures.items():
            if provider != ModelProviderKind.HEURISTIC.value:
                return f"{provider}: {message}"
        return "no model provider answered"

    async def next(self, request: PlanRequest) -> Plan:
        if request.step_index >= request.max_steps - 1:
            # The executor stops after this step, so an answer is the only useful outcome.
            return Plan.finish(
                _budget_report(request),
                thought="Step budget reached; reporting what was gathered so far.",
                provider=self._config.provider,
                model=self._config.name,
            )

        if not request.tools:
            return Plan.finish(
                "This Buttlr has no tools available for this request, so it could not look "
                "anything up. Grant it a tool and run it again.",
                thought="No tools are available, so there is nothing to call.",
                provider=self._config.provider,
                model=self._config.name,
            )

        completion = CompletionRequest(
            messages=_messages(request),
            tools=list(request.tools),
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        try:
            response = await self._models.complete(self._config, completion)
        except ModelError as exc:
            self.last_error = self._degraded_reason()
            raise PlannerError(f"The model could not plan the next step: {exc.message}") from exc
        except TimeoutError as exc:
            self.last_error = "the model timed out"
            raise PlannerError("The model timed out while planning the next step.") from exc
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            self.last_error = f"the response could not be read: {exc}"
            raise PlannerError(f"The model's response could not be read: {exc}") from exc

        if response.provider == ModelProviderKind.HEURISTIC.value:
            # The router walked its whole chain and landed on the deterministic provider. That is
            # not a plan: it is a placeholder, and reporting it as the run's answer would be a
            # lie. Fall back to the planner that actually sequences tools.
            self.last_error = self._degraded_reason()
            raise PlannerError(f"No model answered — {self.last_error}")

        usage = response.usage
        provider = response.provider or self._config.provider
        model = response.model or self._config.name

        if response.tool_calls:
            call = response.tool_calls[0]
            available = {spec.name: spec for spec in request.tools}
            spec = available.get(call.name)
            if spec is None:
                raise PlannerError(
                    f"The model asked for the tool {call.name!r}, which this Buttlr was not "
                    "granted."
                )
            arguments = _arguments(call.arguments, spec)
            return Plan.call(
                call.name,
                arguments,
                thought=response.content or f"Calling {call.name}.",
                usage=usage,
                provider=provider,
                model=model,
            )

        answer = response.content.strip()
        if not answer:
            raise PlannerError("The model returned neither a tool call nor an answer.")
        return Plan.finish(
            answer,
            thought="Answering with the final report.",
            usage=usage,
            provider=provider,
            model=model,
        )


def _messages(request: PlanRequest) -> list[Message]:
    system = (request.system_prompt or "").strip()
    if not system:
        system = "You are a Buttlr: an AI employee that works through a goal using its tools."
    messages = [Message(role="system", content=f"{system}{_SYSTEM_SUFFIX}")]

    opening = [f"Goal: {request.goal.strip() or '(no goal was given)'}"]
    if request.scope:
        opening.append(f"Scope: {_compact(request.scope)}")
    if request.tools:
        opening.append(
            "Tools available: " + ", ".join(spec.name for spec in request.tools)
        )
    opening.append(f"Step {request.step_index + 1} of {request.max_steps}.")
    messages.append(Message(role="user", content="\n".join(opening)))

    for observation in request.observations:
        messages.extend(_observation_turns(observation))

    messages.append(
        Message(
            role="user",
            content=(
                "Choose the single next action now: call one of the tools above, or give the "
                "final answer."
            ),
        )
    )
    return messages


def _observation_turns(observation: Observation) -> list[Message]:
    call = Message(
        role="assistant",
        content=f"Called {observation.tool} with {_compact(observation.arguments)}.",
    )
    if observation.approved is False:
        outcome = "The action was declined in review and was not run."
    elif not observation.ok:
        outcome = observation.summary or "The tool failed without giving a reason."
    else:
        outcome = observation.summary or "The tool succeeded."
        if observation.data is not None:
            outcome = f"{outcome} Data: {_compact(observation.data)}"

    if observation.approved is False and not observation.ok:
        return [
            call,
            Message(role="user", content=f"Result: {outcome}"),
            Message(
                role="assistant",
                content=(
                    "Understood — I will not retry that action and will note it in the report."
                ),
            ),
        ]
    return [call, Message(role="user", content=f"Result: {outcome}")]


def _compact(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - default=str makes this unreachable
        text = str(value)
    if len(text) > _MAX_OBSERVATION_CHARS:
        text = text[: _MAX_OBSERVATION_CHARS - 1].rstrip() + "…"
    return text


def _arguments(raw: dict[str, Any], spec: ToolSpec) -> dict[str, Any]:
    """Drop anything the tool's schema does not declare; never widen a call."""
    properties: dict[str, Any] = spec.parameters.get("properties") or {}
    if not properties:
        return {}
    arguments = {key: value for key, value in raw.items() if key in properties}
    missing = set(spec.parameters.get("required") or ()) - set(arguments)
    if missing:
        raise PlannerError(
            f"The model called {spec.name} without {', '.join(sorted(missing))}."
        )
    return arguments


def _budget_report(request: PlanRequest) -> str:
    observations = request.observations
    if not observations:
        return (
            "The step budget for this run ended before any tool could return data, so there is "
            "nothing to report."
        )
    lines = ["**The run reached its step budget.**", "", "What was gathered before stopping:"]
    for observation in observations:
        if observation.approved is False:
            detail = "declined in review"
        elif not observation.ok:
            detail = observation.summary or "did not complete"
        else:
            detail = observation.summary or "completed"
        lines.append(f"- `{observation.tool}` — {detail}")
    return "\n".join(lines)
