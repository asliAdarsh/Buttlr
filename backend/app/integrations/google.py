"""Google Workspace client: Gmail, Drive, Sheets, Calendar and Docs over REST.

Credentials are ``{access_token, refresh_token, client_id, client_secret,
expiry}``. Access tokens are refreshed in place when they expire — or as soon
as a call comes back 401 — but nothing is persisted here: the caller owns
storage.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

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

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE_BASE = "https://www.googleapis.com/drive/v3"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
DOCS_BASE = "https://docs.googleapis.com/v1/documents"

TIMEOUT_SECONDS = 20.0
#: Refresh slightly before the real expiry so a call never races the clock.
TOKEN_SKEW_SECONDS = 60

_AUTH_MESSAGE = (
    "We couldn't authenticate with Google. Your connection may have expired — "
    "reconnect Google and try again."
)
_REFRESH_MESSAGE = (
    "The Google connection expired and couldn't be refreshed automatically. "
    "Reconnect Google and try again."
)
_NOT_CONNECTED_MESSAGE = (
    "Google isn't connected for this organization. "
    "An administrator can reconnect Google from the Integrations page."
)


class _RetryableError(Exception):
    """Internal marker that makes tenacity retry a 5xx response."""


class GoogleClient:
    """Reads and writes Google Workspace on behalf of a connected organization."""

    def __init__(self, credentials: dict[str, Any]) -> None:
        self._credentials: dict[str, Any] = dict(credentials or {})
        if not self._credentials.get("access_token") and not self._credentials.get(
            "refresh_token"
        ):
            raise IntegrationError(_NOT_CONNECTED_MESSAGE)
        self._client: httpx.AsyncClient | None = None

    # ---- plumbing ---------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> GoogleClient:
        self._http()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _access_token(self) -> str:
        """A valid access token, refreshing the stored credential when needed."""
        token = self._credentials.get("access_token")
        if isinstance(token, str) and token and not self._is_expired():
            return token
        return await self._refresh()

    def _is_expired(self) -> bool:
        expiry = self._credentials.get("expiry")
        parsed = _parse_expiry(expiry)
        if parsed is None:
            # No expiry recorded: trust the token until a call says otherwise.
            return False
        return parsed <= datetime.now(UTC) + timedelta(seconds=TOKEN_SKEW_SECONDS)

    async def _refresh(self) -> str:
        refresh_token = self._credentials.get("refresh_token")
        client_id = self._credentials.get("client_id")
        client_secret = self._credentials.get("client_secret")
        if not refresh_token or not client_id or not client_secret:
            raise IntegrationError(_REFRESH_MESSAGE)

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        client = self._http()
        try:
            response = await client.post(TOKEN_URL, data=data)
        except httpx.HTTPError as exc:
            logger.warning("Google token endpoint unreachable: %s", exc.__class__.__name__)
            raise IntegrationError(
                "We couldn't reach Google to refresh the connection. Please try again."
            ) from exc

        payload = _json_or_empty(response)
        token = payload.get("access_token")
        if response.status_code >= 400 or not isinstance(token, str) or not token:
            logger.warning(
                "Google rejected the refresh request (status=%s)", response.status_code
            )
            raise IntegrationError(_REFRESH_MESSAGE)

        self._credentials["access_token"] = token
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int | float):
            self._credentials["expiry"] = (
                datetime.now(UTC) + timedelta(seconds=float(expires_in))
            ).isoformat()
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            self._credentials["refresh_token"] = rotated
        return token

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call a Google endpoint, refreshing once on 401."""
        token = await self._access_token()
        response = await self._send(method, url, token, params=params, json=json)
        if response.status_code == 401:
            token = await self._refresh()
            response = await self._send(method, url, token, params=params, json=json)
        return self._decode(response)

    async def _send(
        self,
        method: str,
        url: str,
        token: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        client = self._http()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
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
                        method, url, headers=headers, params=params, json=json
                    )
                    if response.status_code >= 500:
                        raise _RetryableError(f"Google returned {response.status_code}")
                break
        except _RetryableError as exc:
            logger.warning("Google %s %s failed after retries: %s", method, url, exc)
            raise IntegrationError(
                "Google is having trouble right now. Please try again in a moment."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Google %s %s transport error: %s", method, url, exc.__class__.__name__
            )
            raise IntegrationError(
                "We couldn't reach Google. Check the connection and try again."
            ) from exc
        return response

    def _decode(self, response: httpx.Response) -> Any:
        status = response.status_code
        if status in (401, 403):
            raise IntegrationError(_AUTH_MESSAGE)
        if status == 404:
            raise IntegrationError(
                "Google couldn't find that item. Check the ID and that the Buttlr's "
                "account has access."
            )
        if status == 429:
            raise IntegrationError(
                "Google's usage limit for this connection was reached. "
                "Wait a few minutes, then try again."
            )
        if status >= 400:
            detail = _error_message(response)
            raise IntegrationError(
                "Google couldn't complete that request"
                + (f": {detail}" if detail else ".")
                + " Please check the details and try again."
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationError(
                "Google returned a response we couldn't read. Please try again."
            ) from exc

    # ---- Gmail ------------------------------------------------------------

    async def gmail_search(
        self, query: str, *, max_results: int = 10
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"{GMAIL_BASE}/messages",
            params={"q": query, "maxResults": max_results},
        )
        messages = payload.get("messages") if isinstance(payload, dict) else None
        return list(messages) if isinstance(messages, list) else []

    async def gmail_get(self, message_id: str) -> dict[str, Any]:
        payload = await self._request(
            "GET", f"{GMAIL_BASE}/messages/{_segment(message_id)}"
        )
        return decode_gmail_message(payload if isinstance(payload, dict) else {})

    async def gmail_send(
        self, *, to: str, subject: str, body: str, cc: str | None = None
    ) -> dict[str, Any]:
        message = EmailMessage()
        message["To"] = to
        if cc:
            message["Cc"] = cc
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        return await self._request(
            "POST",
            f"{GMAIL_BASE}/messages/send",
            json={"raw": raw},
        )

    # ---- Drive ------------------------------------------------------------

    async def drive_search(
        self, query: str, *, max_results: int = 20
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"{DRIVE_BASE}/files",
            params={
                "q": query,
                "pageSize": max_results,
                "fields": (
                    "nextPageToken,files(id,name,mimeType,modifiedTime,size,"
                    "owners(emailAddress),webViewLink,parents,trashed)"
                ),
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
        )
        files = payload.get("files") if isinstance(payload, dict) else None
        return list(files) if isinstance(files, list) else []

    async def drive_get(self, file_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{DRIVE_BASE}/files/{_segment(file_id)}",
            params={
                "fields": (
                    "id,name,mimeType,modifiedTime,createdTime,size,owners(emailAddress),"
                    "webViewLink,parents,description,trashed"
                ),
                "supportsAllDrives": "true",
            },
        )

    # ---- Sheets -----------------------------------------------------------

    async def sheets_read(self, spreadsheet_id: str, cell_range: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{SHEETS_BASE}/{_segment(spreadsheet_id)}/values/{_range(cell_range)}",
        )

    async def sheets_write(
        self, spreadsheet_id: str, cell_range: str, values: list[list[Any]]
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"{SHEETS_BASE}/{_segment(spreadsheet_id)}/values/{_range(cell_range)}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"range": cell_range, "majorDimension": "ROWS", "values": values},
        )

    # ---- Calendar ---------------------------------------------------------

    async def calendar_list(
        self, *, time_min: str | None = None, max_results: int = 20
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        payload = await self._request("GET", CALENDAR_BASE, params=params)
        items = payload.get("items") if isinstance(payload, dict) else None
        return list(items) if isinstance(items, list) else []

    async def calendar_create_event(
        self, *, summary: str, start: str, end: str, description: str = ""
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            body["description"] = description
        return await self._request("POST", CALENDAR_BASE, json=body)

    # ---- Docs -------------------------------------------------------------

    async def docs_get(self, document_id: str) -> dict[str, Any]:
        payload = await self._request(
            "GET", f"{DOCS_BASE}/{_segment(document_id)}"
        )
        if not isinstance(payload, dict):
            return {}
        return {**payload, "text": extract_docs_text(payload.get("body"))}

    # ---- account ----------------------------------------------------------

    async def account(self) -> dict[str, Any]:
        """The connected Google account (``GET /oauth2/v3/userinfo``)."""
        return await self._request(
            "GET", "https://www.googleapis.com/oauth2/v3/userinfo"
        )


# ---- payload helpers ------------------------------------------------------


def decode_gmail_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Gmail message into readable text plus its headers."""
    headers: dict[str, str] = {}
    payload_node = payload.get("payload")
    raw_headers = (
        payload_node.get("headers", []) if isinstance(payload_node, dict) else []
    )
    for header in raw_headers if isinstance(raw_headers, list) else []:
        if isinstance(header, dict) and isinstance(header.get("name"), str):
            headers[header["name"].lower()] = str(header.get("value", ""))


    message: dict[str, Any] = {
        "id": payload.get("id"),
        "thread_id": payload.get("threadId"),
        "snippet": payload.get("snippet", ""),
        "from": headers.get("from"),
        "to": headers.get("to"),
        "cc": headers.get("cc"),
        "subject": headers.get("subject", ""),
        "date": headers.get("date"),
        "labels": list(payload.get("labelIds", []) or []),
        "body": _gmail_text(payload.get("payload")),
    }
    return message


def extract_docs_text(body: Any) -> str:
    """Flatten a Google Docs document body into plain text."""
    lines: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        run = node.get("textRun")
        if isinstance(run, dict):
            lines.append(str(run.get("content", "")))
            return
        if node.get("type") == "paragraph":
            walk(node.get("paragraph", node.get("elements")))
            lines.append("\n")
            return
        if node.get("type") == "table":
            walk(node.get("table"))
            return
        for value in node.values():
            walk(value)

    walk(body.get("content") if isinstance(body, dict) else body)
    return "".join(lines)


def _gmail_text(part: Any) -> str:
    """Collect the readable body of a Gmail payload tree."""
    if not isinstance(part, dict):
        return ""
    mime = str(part.get("mimeType", ""))
    data = _body_data(part)
    if data and mime == "text/plain":
        decoded = _decode_base64(data)
        if decoded:
            return decoded
    chunks: list[str] = []
    children = part.get("parts")
    for child in children if isinstance(children, list) else []:
        text = _gmail_text(child)
        if text:
            chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    if data and mime.startswith("text/"):
        return _decode_base64(data)
    return ""


def _body_data(part: dict[str, Any]) -> str:
    body = part.get("body")
    if not isinstance(body, dict):
        return ""
    data = body.get("data")
    return data if isinstance(data, str) else ""


def _decode_base64(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""


def _parse_expiry(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _segment(value: str) -> str:
    return str(value or "").strip().strip("/")


def _range(cell_range: str) -> str:
    """URL-encode a Sheets A1 range, keeping its ``:`` separator intact."""
    return quote(str(cell_range or "").strip(), safe=":$")


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


def _error_message(response: httpx.Response) -> str:
    payload = _json_or_empty(response)
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message.strip()[:400]
    if isinstance(error, str):
        return error.strip()[:400]
    return ""
