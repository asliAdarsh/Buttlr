"""OAuth 2.0 helpers for the GitHub and Google connections.

Library-first: ``httpx`` performs the token calls and PyJWT signs the ``state``
parameter. No hand-rolled crypto, no extra dependency.

The ``state`` parameter is a short-lived HS256 JWT that binds the authorization
request to one organization and one redirect URI, so a callback cannot be
replayed against a different organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from app.core.config import Settings
from app.core.errors import IntegrationError, ValidationError
from app.core.logging import get_logger
from app.schemas.enums import IntegrationProvider

logger = get_logger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GITHUB_SCOPES: tuple[str, ...] = ("repo", "read:org", "workflow")
GOOGLE_SCOPES: tuple[str, ...] = (
    "gmail.readonly",
    "gmail.send",
    "drive.readonly",
    "spreadsheets",
    "calendar",
    "documents.readonly",
)

#: How long an authorization request stays valid.
STATE_TTL = timedelta(minutes=10)

_TOKEN_TIMEOUT_SECONDS = 20.0
_UNCONFIGURED: dict[IntegrationProvider, str] = {
    IntegrationProvider.GITHUB: (
        "GitHub sign-in isn't configured on this workspace yet. "
        "An administrator can connect GitHub with a personal access token instead."
    ),
    IntegrationProvider.GOOGLE: (
        "Google sign-in isn't configured on this workspace yet. "
        "An administrator needs to register a Google OAuth client before "
        "Google Workspace can be connected."
    ),
}


@dataclass(frozen=True)
class OAuthProviderConfig:
    """Everything needed to run one provider's authorization-code flow."""

    provider: IntegrationProvider
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    client_id: str | None
    client_secret: str | None
    extra_authorize_params: dict[str, str] = field(default_factory=dict)


def provider_config(
    provider: IntegrationProvider, settings: Settings
) -> OAuthProviderConfig | None:
    """Return the provider's OAuth configuration, or ``None`` when it is not set up."""
    if provider is IntegrationProvider.GITHUB:
        client_id = settings.github_oauth_client_id
        client_secret = settings.github_oauth_client_secret
        if not client_id or not client_secret:
            return None
        return OAuthProviderConfig(
            provider=IntegrationProvider.GITHUB,
            authorize_url=GITHUB_AUTHORIZE_URL,
            token_url=GITHUB_TOKEN_URL,
            scopes=GITHUB_SCOPES,
            client_id=client_id,
            client_secret=client_secret,
            # No GitHub sign-ups, and no PKCE: GitHub supports neither here.
            extra_authorize_params={"allow_signup": "false"},
        )

    if provider is IntegrationProvider.GOOGLE:
        client_id = settings.google_oauth_client_id
        client_secret = settings.google_oauth_client_secret
        if not client_id or not client_secret:
            return None
        return OAuthProviderConfig(
            provider=IntegrationProvider.GOOGLE,
            authorize_url=GOOGLE_AUTHORIZE_URL,
            token_url=GOOGLE_TOKEN_URL,
            scopes=GOOGLE_SCOPES,
            client_id=client_id,
            client_secret=client_secret,
            extra_authorize_params={
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            },
        )

    return None


def provider_display_name(provider: IntegrationProvider) -> str:
    if provider is IntegrationProvider.GITHUB:
        return "GitHub"
    if provider is IntegrationProvider.GOOGLE:
        return "Google"
    if provider is IntegrationProvider.JIRA:
        return "Jira"
    return provider.value.title()


def require_provider_config(
    provider: IntegrationProvider, settings: Settings
) -> OAuthProviderConfig:
    """Like :func:`provider_config`, but raises a user-facing error when unconfigured."""
    config = provider_config(provider, settings)
    if config is None:
        raise ValidationError(_UNCONFIGURED.get(provider, "That connection isn't available."))
    return config


def build_authorization_url(
    config: OAuthProviderConfig, redirect_uri: str, state: str
) -> str:
    """Compose the provider's consent URL for the given redirect and state."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id or "",
        "redirect_uri": redirect_uri,
        "scope": " ".join(config.scopes),
        "state": state,
    }
    params.update(config.extra_authorize_params)
    return str(httpx.URL(config.authorize_url, params=params))


async def exchange_code(
    config: OAuthProviderConfig, code: str, redirect_uri: str
) -> dict[str, Any]:
    """Trade an authorization ``code`` for a token payload."""
    payload = {
        "client_id": config.client_id or "",
        "client_secret": config.client_secret or "",
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    return await _token_request(config, payload)


async def refresh_access_token(
    config: OAuthProviderConfig, refresh_token: str
) -> dict[str, Any]:
    """Exchange a refresh token for a fresh access token."""
    payload = {
        "client_id": config.client_id or "",
        "client_secret": config.client_secret or "",
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    return await _token_request(config, payload)


async def _token_request(
    config: OAuthProviderConfig, data: dict[str, str]
) -> dict[str, Any]:
    name = provider_display_name(config.provider)
    headers = {"Accept": "application/json"}
    if config.provider is IntegrationProvider.GITHUB:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT_SECONDS) as client:
            response = await client.post(
                config.token_url, data=data, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.warning("%s token endpoint unreachable: %s", name, exc.__class__.__name__)
        raise IntegrationError(
            f"We couldn't reach {name} to finish the connection. Please try again."
        ) from exc

    body = _json_or_empty(response)
    if response.status_code >= 400 or body.get("error"):
        detail = str(body.get("error_description") or body.get("error") or "").strip()
        logger.warning(
            "%s rejected the token request (status=%s, error=%s)",
            name,
            response.status_code,
            detail or "unspecified",
        )
        raise IntegrationError(
            f"{name} refused to complete the connection"
            + (f": {detail}" if detail else ".")
            + " Please reconnect and try again."
        )
    if "access_token" not in body:
        raise IntegrationError(
            f"{name} returned an unexpected token response. Please try reconnecting."
        )
    return body


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def sign_state(
    provider: IntegrationProvider, organization_id: str, redirect_uri: str, secret: str
) -> str:
    """Sign the ``state`` parameter that ties a callback to this organization."""
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "provider": provider.value,
        "org": organization_id,
        "redirect": redirect_uri,
        "iat": int(now.timestamp()),
        "exp": int((now + STATE_TTL).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def verify_state(state: str, secret: str) -> dict[str, Any]:
    """Validate a ``state`` JWT and return its claims."""
    if not state:
        raise ValidationError("This connection request expired. Please start again.")
    try:
        claims = jwt.decode(state, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ValidationError(
            "This connection request expired. Please start again."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise ValidationError(
            "This connection request is not valid. Please start again."
        ) from exc

    missing = [key for key in ("provider", "org", "redirect") if not claims.get(key)]
    if missing:
        raise ValidationError(
            "This connection request is not valid. Please start again."
        )
    return claims
