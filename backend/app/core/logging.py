"""Logging and per-request context.

Uses the standard library so the backend has no logging dependency. ``log_json`` switches
between human-readable and JSON output (production log aggregators).
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import settings

_request_id: ContextVar[str | None] = ContextVar("buttlr_request_id", default=None)
_org_id: ContextVar[str | None] = ContextVar("buttlr_org_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("buttlr_user_id", default=None)
_execution_id: ContextVar[str | None] = ContextVar("buttlr_execution_id", default=None)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or "-"
        record.organization_id = _org_id.get() or "-"
        record.user_id = _user_id.get() or "-"
        record.execution_id = _execution_id.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "organization_id": getattr(record, "organization_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "execution_id": getattr(record, "execution_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, '%H:%M:%S')} "
            f"{record.levelname:<8} {record.name:<28} {record.getMessage()}"
        )
        extra = []
        for key in ("request_id", "organization_id", "execution_id"):
            value = getattr(record, key, "-")
            if value and value != "-":
                extra.append(f"{key}={value}")
        if extra:
            base += "  [" + " ".join(extra) + "]"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if settings.log_json else TextFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_context(
    *,
    request_id: str | None = None,
    organization_id: str | None = None,
    user_id: str | None = None,
    execution_id: str | None = None,
) -> None:
    if request_id is not None:
        _request_id.set(request_id)
    if organization_id is not None:
        _org_id.set(organization_id)
    if user_id is not None:
        _user_id.set(user_id)
    if execution_id is not None:
        _execution_id.set(execution_id)


def current_request_id() -> str | None:
    return _request_id.get()


def current_execution_id() -> str | None:
    return _execution_id.get()


def reset_request_context() -> None:
    _request_id.set(None)
    _org_id.set(None)
    _user_id.set(None)
    _execution_id.set(None)
