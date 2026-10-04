"""Generic API envelopes and helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    """Base for stored documents: ignores unknown fields written by newer versions."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", use_enum_values=False)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Ack(BaseModel):
    ok: bool = True
    message: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
