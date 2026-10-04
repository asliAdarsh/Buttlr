"""Structured error types.

Every error carries a machine-readable ``code`` and a human ``message`` that is safe to
show in the UI. Technical detail stays in the logs.
"""

from __future__ import annotations

from typing import Any


class ButtlrError(Exception):
    """Base class for expected, user-facing failures."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}

    def to_payload(self, request_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        if request_id:
            payload["request_id"] = request_id
        return payload


class PermissionDeniedError(ButtlrError):
    status_code = 403
    code = "permission_denied"


class UnauthenticatedError(ButtlrError):
    status_code = 401
    code = "unauthenticated"


class NotFoundError(ButtlrError):
    status_code = 404
    code = "not_found"


class ConflictError(ButtlrError):
    status_code = 409
    code = "conflict"


class ValidationError(ButtlrError):
    status_code = 422
    code = "validation_error"


class IntegrationError(ButtlrError):
    status_code = 502
    code = "integration_error"


class ToolExecutionError(ButtlrError):
    status_code = 502
    code = "tool_execution_error"


class ModelError(ButtlrError):
    status_code = 502
    code = "model_error"


class ApprovalRequiredError(ButtlrError):
    status_code = 409
    code = "approval_required"
