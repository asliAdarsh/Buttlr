"""GitHub REST client.

One lazily-created ``httpx.AsyncClient`` per instance, retried on transport
errors and 5xx, with every failure turned into an actionable
:class:`~app.core.errors.IntegrationError`. The token is never logged.
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

DEFAULT_BASE_URL = "https://api.github.com"
TIMEOUT_SECONDS = 20.0

_AUTH_MESSAGE = (
    "We couldn't authenticate with GitHub. Your connection may have expired — "
    "reconnect GitHub and try again."
)
_RATE_LIMIT_MESSAGE = (
    "GitHub's rate limit for this connection has been reached. "
    "Wait a few minutes, then try again."
)


class _RetryableError(Exception):
    """Internal marker that makes tenacity retry a 5xx response."""


class GitHubClient:
    """Reads and writes GitHub on behalf of a connected organization."""

    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL) -> None:
        if not token:
            raise IntegrationError(
                "GitHub isn't connected for this organization. "
                "An administrator can reconnect GitHub from the Integrations page."
            )
        self._token = token
        self._base_url = base_url.rstrip("/") or DEFAULT_BASE_URL
        self._client: httpx.AsyncClient | None = None

    # ---- plumbing ---------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Buttlr",
        }

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self.headers,
                timeout=TIMEOUT_SECONDS,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GitHubClient:
        self._http()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Perform one GitHub call, retrying transport errors and 5xx."""
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
                        method, path, params=_clean(params), json=json
                    )
                    if response.status_code >= 500:
                        raise _RetryableError(f"GitHub returned {response.status_code}")
                break
        except _RetryableError as exc:
            logger.warning("GitHub %s %s failed after retries: %s", method, path, exc)
            raise IntegrationError(
                "GitHub is having trouble right now. Please try again in a moment."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "GitHub %s %s transport error: %s", method, path, exc.__class__.__name__
            )
            raise IntegrationError(
                "We couldn't reach GitHub. Check the connection and try again."
            ) from exc
        return self._decode(response)

    def _decode(self, response: httpx.Response) -> Any:
        status = response.status_code
        if status == 401:
            raise IntegrationError(_AUTH_MESSAGE)
        if status == 403:
            if _is_rate_limited(response):
                raise IntegrationError(_RATE_LIMIT_MESSAGE)
            raise IntegrationError(_AUTH_MESSAGE)
        if status == 404:
            raise IntegrationError(_not_found_message(response))
        if status == 422:
            detail = _error_message(response)
            raise IntegrationError(
                "GitHub rejected that change"
                + (f": {detail}" if detail else ".")
                + " Please check the details and try again."
            )
        if status >= 400:
            detail = _error_message(response)
            raise IntegrationError(
                "GitHub couldn't complete that request"
                + (f": {detail}" if detail else ".")
                + " Please try again."
            )
        if status == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationError(
                "GitHub returned a response we couldn't read. Please try again."
            ) from exc

    # ---- account ----------------------------------------------------------

    async def get_user(self) -> dict[str, Any]:
        """The authenticated user (``GET /user``)."""
        return await self._request("GET", "/user")

    # ---- repositories -----------------------------------------------------

    async def list_repositories(
        self, *, per_page: int = 100, page: int = 1, sort: str = "updated"
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "/user/repos",
            params={"per_page": per_page, "page": page, "sort": sort},
        )

    async def get_repository(self, repo: str) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{_clean_repo(repo)}")

    # ---- pull requests ----------------------------------------------------

    async def list_pull_requests(
        self,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 50,
        sort: str = "updated",
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            f"/repos/{_clean_repo(repo)}/pulls",
            params={"state": state, "per_page": per_page, "sort": sort},
        )

    async def get_pull_request(self, repo: str, number: int) -> dict[str, Any]:
        return await self._request(
            "GET", f"/repos/{_clean_repo(repo)}/pulls/{int(number)}"
        )

    async def list_pull_request_files(
        self, repo: str, number: int
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/repos/{_clean_repo(repo)}/pulls/{int(number)}/files"
        )

    async def list_pull_request_comments(
        self, repo: str, number: int
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/repos/{_clean_repo(repo)}/pulls/{int(number)}/comments"
        )

    # ---- issues -----------------------------------------------------------

    async def list_issues(
        self,
        repo: str,
        *,
        state: str = "open",
        labels: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = labels
        return await self._request(
            "GET", f"/repos/{_clean_repo(repo)}/issues", params=params
        )

    async def search_issues(
        self, query: str, *, per_page: int = 25
    ) -> list[dict[str, Any]]:
        result = await self._request(
            "GET",
            "/search/issues",
            params={"q": query, "per_page": per_page},
        )
        items = result.get("items") if isinstance(result, dict) else None
        return list(items or [])

    async def create_issue(
        self,
        repo: str,
        *,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = list(labels)
        return await self._request(
            "POST", f"/repos/{_clean_repo(repo)}/issues", json=payload
        )

    async def add_comment(
        self, repo: str, issue_number: int, body: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/repos/{_clean_repo(repo)}/issues/{int(issue_number)}/comments",
            json={"body": body},
        )


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, _RetryableError):
        return True
    return isinstance(
        exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)
    )


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    remaining = response.headers.get("x-ratelimit-remaining")
    if remaining is not None and remaining.strip() == "0":
        return True
    message = _error_message(response).lower()
    return "rate limit" in message


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    message = body.get("message")
    if isinstance(message, str):
        return message.strip()
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            detail = first.get("message") or first.get("code")
            if isinstance(detail, str):
                return detail.strip()
    return ""


def _not_found_message(response: httpx.Response) -> str:
    detail = _error_message(response)
    lowered = detail.lower()
    if "pull request" in lowered:
        target = f"That pull request ({detail})"
    elif "issue" in lowered:
        target = f"That issue ({detail})"
    elif "repository" in lowered or "not found" in lowered:
        target = f"That repository ({detail})" if detail else "That repository"
    else:
        target = f"That GitHub resource ({detail})" if detail else "That GitHub resource"
    return f"{target} wasn't found. Check the name and that the Buttlr's account has access."


def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _clean_repo(repo: str) -> str:
    """Normalise ``owner/name``, stripping a GitHub URL or a leading slash."""
    value = (repo or "").strip()
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix) :]
            break
    return value.strip("/")
