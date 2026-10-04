"""Bring-your-own model providers.

A workspace can configure the model it reasons with from inside the application, either with a
provider API key or by pointing at a local server. The stored key is encrypted at rest and is
never returned by the API — only whether one is set.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.common import DomainModel


class ModelProviderEntry(DomainModel):
    """One selectable model provider, and where its credentials came from."""

    provider: str
    name: str
    kind: str  # "cloud" | "local" | "builtin"
    description: str = ""
    configured: bool = False
    #: ``workspace`` when this organization supplied credentials, ``deployment`` when the
    #: server's environment did, ``None`` when nothing is configured.
    source: str | None = None
    model: str | None = None
    base_url: str | None = None
    requires_key: bool = True
    requires_base_url: bool = False
    docs_url: str | None = None
    note: str = ""


class ModelProviderUpdate(DomainModel):
    """Credentials for one provider, as entered in the application."""

    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=120)
