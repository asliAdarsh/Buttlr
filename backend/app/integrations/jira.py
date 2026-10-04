"""Jira Cloud REST client (v3, with v2 fallback for JQL search).

Authentication is HTTP basic with an Atlassian account email and an API token.
Cloud deployments take Atlassian Document Format for descriptions and comments;
Server/Data Center deployments take plain strings.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.errors import IntegrationError
from app.core.logging import get_logger

logger = get_logger(__name__)

TIMEOUT_SECONDS = 20.0

_AUTH_MESSAGE = (
    "We couldn't authenticate with Jira. Your connection may have expired — "
    "reconnect Jira and try again."
)
_BASE_URL_MESSAGE = (
    "The Jira site URL looks incorrect. Expected something like https://yourteam.atlassian.net."
)


class _RetryableError(Exception):
    """Internal marker that makes tenacity retry a 5xx response."""


class JiraClient:
    """Reads and writes Jira Cloud issues on behalf of a connected organization."""

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        normalised = (base_url or "").strip().rstrip("/")
        if not normalised:
            raise IntegrationError(_BASE_URL_MESSAGE)
        if not normalised.startswith(("http://", "https://")):
            normalised = f"https://{normalised}"
        if not email or not api_token:
            raise IntegrationError(
                "Jira needs both an account email and an API token. "
                "Reconnect Jira with both and try again."
            )
        self.base_url = normalised
        self._email = email
        self._api_token = api_token
        self._client: httpx.AsyncClient | None = None

    # ---- plumbing ---------------------------------------------------------

    @property
    def is_cloud(self) -> bool:
        """Cloud deployments require Atlassian Document Format bodies."""
        host = self.base_url.split("://", 1)[-1].split("/", 1)[0].lower()
        return host.endswith(".atlassian.net") or host.endswith(".jira.com")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self._email, self._api_token),
                headers={"Accept": "application/json"},
                timeout=TIMEOUT_SECONDS,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> JiraClient:
        self._http()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        client = self._http()
        retrying = AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception(_should_retry),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    response = await client.request(
                        method, path, json=json, params=params
                    )
                    if response.status_code >= 500:
                        raise _RetryableError(f"Jira returned {response.status_code}")
                break
        except _RetryableError as exc:
            logger.warning("Jira %s %s failed after retries: %s", method, path, exc)
            raise IntegrationError(
                "Jira is having trouble right now. Please try again in a moment."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Jira %s %s transport error: %s", method, path, exc.__class__.__name__
            )
            raise IntegrationError(
                "We couldn't reach Jira. Check the connection and try again."
            ) from exc
        return response

    def _check(self, response: httpx.Response, action: str) -> httpx.Response:
        status = response.status_code
        if status == 401:
            raise IntegrationError(_AUTH_MESSAGE)
        if status == 403:
            raise IntegrationError(
                "That Buttlr's Jira account doesn't have permission to "
                f"{action}. Grant access in Jira, then try again."
            )
        if status == 404:
            detail = _error_message(response)
            target = detail or "that item"
            raise IntegrationError(
                f"Jira couldn't find {target} while trying to {action}. "
                "Check the project key or issue ID and try again."
            )
        if status >= 400:
            detail = _error_message(response)
            raise IntegrationError(
                f"Jira couldn't {action}"
                + (f": {detail}" if detail else ".")
                + " Please check the details and try again."
            )
        return response

    async def _json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        action: str = "complete that request",
    ) -> Any:
        response = await self._send(method, path, json=json, params=params)
        self._check(response, action)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationError(
                "Jira returned a response we couldn't read. Please try again."
            ) from exc

    def _text_body(self, text: str) -> Any:
        """Wrap plain text in Atlassian Document Format for Cloud deployments."""
        if not self.is_cloud:
            return text
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }

    # ---- account ----------------------------------------------------------

    async def myself(self) -> dict[str, Any]:
        """The authenticated account (``GET /rest/api/3/myself``)."""
        return await self._json(
            "GET", "/rest/api/3/myself", action="identify the account"
        )

    async def list_projects(self) -> list[dict[str, Any]]:
        """Every project visible to the account."""
        response = await self._send(
            "GET", "/rest/api/3/project/search", params={"maxResults": 100}
        )
        if response.status_code in (404, 405):
            # Older or restricted deployments only expose the v2 collection endpoint.
            response = await self._send("GET", "/rest/api/2/project")
        self._check(response, "list projects")
        payload = _json_or_any(response)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, list):
                return [item for item in values if isinstance(item, dict)]
        return []

    # ---- issues -----------------------------------------------------------

    async def search_issues(
        self, jql: str, *, max_results: int = 25
    ) -> list[dict[str, Any]]:
        """Run a JQL search, tolerating the v3 search-endpoint migration."""
        body = {"jql": jql, "maxResults": max_results}
        query = {"jql": jql, "maxResults": max_results}
        attempts: tuple[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None], ...] = (
            # The current endpoint, the migrated ``/search/jql`` (query string), then v2.
            ("POST", "/rest/api/3/search", body, None),
            ("GET", "/rest/api/3/search/jql", None, query),
            ("POST", "/rest/api/2/search", body, None),
        )
        first_failure: httpx.Response | None = None
        for method, path, json_body, params in attempts:
            response = await self._send(method, path, json=json_body, params=params)
            if response.status_code in (400, 404, 405, 501):
                # This deployment doesn't serve that endpoint or that JQL shape.
                if first_failure is None:
                    first_failure = response
                continue
            self._check(response, "run that search")
            data = _json_or_empty(response)
            issues = data.get("issues")
            return list(issues) if isinstance(issues, list) else []

        if first_failure is not None:
            self._check(first_failure, "run that search")
        return []

    async def create_issue(
        self,
        *,
        project_key: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = self._text_body(description)
        return await self._json(
            "POST",
            "/rest/api/3/issue",
            json={"fields": fields},
            action="create that issue",
        )

    async def update_issue(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload_fields = dict(fields)
        description = payload_fields.get("description")
        if isinstance(description, str):
            payload_fields["description"] = self._text_body(description)
        return await self._json(
            "PUT",
            f"/rest/api/3/issue/{_clean_key(key)}",
            json={"fields": payload_fields},
            action="update that issue",
        )

    async def add_comment(self, key: str, body: str) -> dict[str, Any]:
        return await self._json(
            "POST",
            f"/rest/api/3/issue/{_clean_key(key)}/comment",
            json={"body": self._text_body(body)},
            action="add that comment",
        )


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, _RetryableError):
        return True
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        ),
    )


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_or_any(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def _error_message(response: httpx.Response) -> str:
    payload = _json_or_empty(response)
    messages: list[str] = []
    raw = payload.get("errorMessages")
    if isinstance(raw, list):
        messages.extend(str(item) for item in raw if item)
    errors = payload.get("errors")
    if isinstance(errors, dict):
        messages.extend(f"{key}: {value}" for key, value in errors.items())
    if not messages:
        single = payload.get("error")
        if isinstance(single, str):
            messages.append(single)
    return "; ".join(messages)[:400]


def _clean_key(key: str) -> str:
    return (key or "").strip().strip("/")
