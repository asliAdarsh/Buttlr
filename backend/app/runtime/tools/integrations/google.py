"""Google tools.

Gmail, Drive, Sheets, Calendar and Docs over one `GoogleClient`. Scope keys are honoured
per surface: ``file_ids``/``folders`` for Drive and Docs, ``spreadsheets`` for Sheets,
``calendars`` for Calendar and ``query`` as the default search for Gmail and Drive.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.integrations.google import GoogleClient
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.integrations import (
    call,
    dry_run_refusal,
    list_summary,
    not_connected,
    outside_scope,
    page_limit,
    query_summary,
    scope_values,
    trim_text,
)
from app.schemas.enums import Permission, RiskLevel

PROVIDER = "google"


def _client(ctx: ToolContext) -> GoogleClient | ToolResult:
    credentials = ctx.credentials.get(PROVIDER) or {}
    if not (credentials.get("access_token") or credentials.get("refresh_token")):
        return not_connected(PROVIDER)
    return GoogleClient(credentials)


def _files_in_scope(ctx: ToolContext) -> list[str]:
    return scope_values(ctx, PROVIDER, "file_ids")


def _file_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "mime_type": item.get("mimeType"),
        "size": item.get("size"),
        "owners": [
            owner.get("emailAddress") or owner.get("displayName")
            for owner in (item.get("owners") or [])
        ],
        "modified_time": item.get("modifiedTime"),
        "created_time": item.get("createdTime"),
        "web_url": item.get("webViewLink"),
        "parents": item.get("parents") or [],
    }


def _message_view(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "subject": message.get("subject"),
        "from": message.get("from"),
        "to": message.get("to"),
        "date": message.get("date"),
        "snippet": trim_text(message.get("snippet"), 400),
        "labels": message.get("labelIds") or [],
    }


def _event_view(event: dict[str, Any]) -> dict[str, Any]:
    start = event.get("start") or {}
    end = event.get("end") or {}
    organizer = event.get("organizer") or {}
    return {
        "id": event.get("id"),
        "summary": event.get("summary"),
        "description": trim_text(event.get("description"), 500),
        "location": event.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": bool(start.get("date")) if isinstance(start, dict) else False,
        "organizer": organizer.get("email") or organizer.get("displayName"),
        "attendees": [
            attendee.get("email") for attendee in (event.get("attendees") or []) if attendee
        ],
        "status": event.get("status"),
        "html_link": event.get("htmlLink"),
    }


class SearchMessages(Tool):
    name = "gmail.search_messages"
    description = (
        "Search Gmail using Gmail search syntax and return matching messages with sender, "
        "subject, date and a short snippet."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        query: str = Field(
            default="",
            description="Gmail query, for example 'from:ana is:unread newer_than:7d'.",
        )
        max_results: int = Field(
            default=10, ge=1, le=50, description="Maximum number of messages to return."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        query = str(args.get("query") or "").strip()
        default_query = scope_values(ctx, PROVIDER, "query")
        if not query:
            query = default_query[0] if default_query else "in:anywhere"
        elif default_query:
            clause = " ".join(f"{{{part}}}" for part in default_query)
            query = f"{query} {clause}"
        try:
            messages, failure = await call(
                client.gmail_search(query, max_results=page_limit(args.get("max_results", 10), 50)),
                action="gmail.search_messages",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [_message_view(message) for message in messages or []]
        return ToolResult.success(
            query_summary(len(views), "message", query),
            data={"messages": views, "query": query},
            query=query,
            count=len(views),
        )


class GetMessage(Tool):
    name = "gmail.get_message"
    description = "Read one email in full, including its decoded plain-text body."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        message_id: str = Field(description="Gmail message id from a search result.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        message_id = str(args["message_id"]).strip()
        try:
            message, failure = await call(
                client.gmail_get(message_id),
                action=f"gmail.get_message[{message_id}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure
        if not message:
            return ToolResult.failure(f"Message {message_id} was not found.")

        data = _message_view(message)
        data["body"] = trim_text(message.get("body"))
        return ToolResult.success(
            f"Read “{data['subject'] or 'no subject'}” from {data['from'] or 'an unknown sender'}.",
            data=data,
            message_id=message_id,
        )


class SendMessage(Tool):
    name = "gmail.send_message"
    description = "Send an email from the connected Gmail account."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.HIGH
    read_only = False

    class Input(BaseModel):
        to: str = Field(description="Recipient email address.")
        subject: str = Field(description="Subject line.")
        body: str = Field(description="Plain-text body of the email.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        try:
            message, failure = await call(
                client.gmail_send(
                    to=args["to"], subject=args["subject"], body=args["body"]
                ),
                action="gmail.send_message",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        data = _message_view(message or {})
        return ToolResult.success(
            f"Sent “{args['subject']}” to {args['to']}.",
            data={"message_id": data.get("id"), "thread_id": data.get("thread_id"), "to": args["to"]},
            message_id=data.get("id"),
            to=args["to"],
        )


class SearchFiles(Tool):
    name = "drive.search_files"
    description = "Search Google Drive files by name or content and return their metadata."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        query: str = Field(default="", description="Drive query text, for example 'quarterly report'.")
        max_results: int = Field(
            default=20, ge=1, le=100, description="Maximum number of files to return."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        query = str(args.get("query") or "").strip()
        default_query = scope_values(ctx, PROVIDER, "query")
        if not query:
            query = default_query[0] if default_query else ""
        allowed_files = _files_in_scope(ctx)
        try:
            files, failure = await call(
                client.drive_search(query, max_results=page_limit(args.get("max_results", 20), 100)),
                action="drive.search_files",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [_file_view(item) for item in files or []]
        if allowed_files:
            views = [view for view in views if view["id"] in allowed_files]
        return ToolResult.success(
            query_summary(len(views), "file", query) if query else list_summary(len(views), "file", ""),
            data={"files": views, "query": query},
            query=query,
            count=len(views),
        )


class GetFile(Tool):
    name = "drive.get_file"
    description = "Get one Google Drive file's metadata by id."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        file_id: str = Field(description="Google Drive file id.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        file_id = str(args["file_id"]).strip()
        try:
            denial = _drive_scope_check(ctx, file_id)
            if denial is not None:
                return denial
            item, failure = await call(
                client.drive_get(file_id), action=f"drive.get_file[{file_id}]"
            )
        finally:
            await client.close()
        if failure is not None:
            return failure
        if not item:
            return ToolResult.failure(f"File {file_id} was not found.")

        data = _file_view(item)
        return ToolResult.success(
            f"Found Drive file “{data['name'] or file_id}”.",
            data=data,
            file_id=file_id,
        )


def _drive_scope_check(ctx: ToolContext, file_id: str) -> ToolResult | None:
    allowed = _files_in_scope(ctx)
    if allowed and file_id not in allowed:
        return outside_scope("files", file_id, allowed)
    return None


class ReadRange(Tool):
    name = "sheets.read_range"
    description = (
        "Read a range of cells from a Google Sheet, for example 'Sheet1!A1:D20'."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        spreadsheet_id: str = Field(description="Google Sheets spreadsheet id.")
        cell_range: str = Field(description="A1 notation range, for example 'Sheet1!A1:D20'.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        spreadsheet_id = str(args["spreadsheet_id"]).strip()
        cell_range = str(args["cell_range"]).strip()
        try:
            denial = _sheet_scope_check(ctx, spreadsheet_id)
            if denial is not None:
                return denial
            payload, failure = await call(
                client.sheets_read(spreadsheet_id, cell_range),
                action=f"sheets.read_range[{spreadsheet_id}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        values = (payload or {}).get("values") or []
        rows = [[trim_text(cell) for cell in row] for row in values[:100]]
        return ToolResult.success(
            f"Read {len(values)} row(s) from {cell_range} in sheet {spreadsheet_id}.",
            data={"values": rows, "range": cell_range, "spreadsheet_id": spreadsheet_id},
            spreadsheet_id=spreadsheet_id,
            cell_range=cell_range,
            rows=len(values),
        )


class WriteRange(Tool):
    name = "sheets.write_range"
    description = "Write values into a range of cells in a Google Sheet."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.MEDIUM
    read_only = False

    class Input(BaseModel):
        spreadsheet_id: str = Field(description="Google Sheets spreadsheet id.")
        cell_range: str = Field(description="A1 notation range to write, for example 'Sheet1!A1'.")
        values: list[list[str]] = Field(
            description="Rows of cell values to write, in order."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        spreadsheet_id = str(args["spreadsheet_id"]).strip()
        cell_range = str(args["cell_range"]).strip()
        values = [[str(cell) for cell in row] for row in (args.get("values") or [])]
        if not values:
            return ToolResult.failure("No values were supplied to write to the sheet.")
        try:
            denial = _sheet_scope_check(ctx, spreadsheet_id)
            if denial is not None:
                return denial
            payload, failure = await call(
                client.sheets_write(spreadsheet_id, cell_range, values),
                action=f"sheets.write_range[{spreadsheet_id}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        updated = (payload or {}).get("updatedRows")
        written = int(updated) if isinstance(updated, int) else len(values)
        return ToolResult.success(
            f"Wrote {written} row(s) to {cell_range} in sheet {spreadsheet_id}.",
            data={"updated_range": (payload or {}).get("updatedRange", cell_range)},
            spreadsheet_id=spreadsheet_id,
            cell_range=cell_range,
            rows_written=written,
        )


def _sheet_scope_check(ctx: ToolContext, spreadsheet_id: str) -> ToolResult | None:
    allowed = scope_values(ctx, PROVIDER, "spreadsheets")
    if allowed and spreadsheet_id not in allowed:
        return outside_scope("spreadsheets", spreadsheet_id, allowed)
    return None


class ListEvents(Tool):
    name = "calendar.list_events"
    description = "List Google Calendar events, optionally starting from a given time."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        time_min: str | None = Field(
            default=None,
            description="ISO 8601 lower bound, for example '2026-01-01T00:00:00Z'.",
        )
        max_results: int = Field(
            default=20, ge=1, le=100, description="Maximum number of events to return."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        time_min = args.get("time_min") or None
        try:
            events, failure = await call(
                client.calendar_list(
                    time_min=time_min, max_results=page_limit(args.get("max_results", 20), 100)
                ),
                action="calendar.list_events",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [_event_view(event) for event in events or []]
        return ToolResult.success(
            f"Found {len(views)} event(s) on the calendar.",
            data={"events": views, "time_min": time_min},
            count=len(views),
        )


class CreateEvent(Tool):
    name = "calendar.create_event"
    description = "Create a Google Calendar event with a start and end time."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.HIGH
    read_only = False

    class Input(BaseModel):
        summary: str = Field(description="Event title.")
        start: str = Field(description="ISO 8601 start time.")
        end: str = Field(description="ISO 8601 end time.")
        description: str = Field(default="", description="Event description.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        try:
            event, failure = await call(
                client.calendar_create_event(
                    summary=args["summary"],
                    start=args["start"],
                    end=args["end"],
                    description=args.get("description") or "",
                ),
                action="calendar.create_event",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        data = _event_view(event or {})
        return ToolResult.success(
            f"Created calendar event “{args['summary']}” from {data['start']} to {data['end']}.",
            data=data,
            event_id=data["id"],
        )


class GetDocument(Tool):
    name = "docs.get_document"
    description = "Read a Google Doc and return its text content."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        document_id: str = Field(description="Google Docs document id.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        document_id = str(args["document_id"]).strip()
        try:
            denial = _drive_scope_check(ctx, document_id)
            if denial is not None:
                return denial
            document, failure = await call(
                client.docs_get(document_id), action=f"docs.get_document[{document_id}]"
            )
        finally:
            await client.close()
        if failure is not None:
            return failure
        if not document:
            return ToolResult.failure(f"Document {document_id} was not found.")

        text = trim_text(document.get("text"))
        return ToolResult.success(
            f"Read document “{document.get('title') or document_id}”.",
            data={
                "document_id": document.get("id", document_id),
                "title": document.get("title"),
                "text": text,
            },
            document_id=document_id,
            title=document.get("title"),
        )


__all__ = [
    "CreateEvent",
    "GetDocument",
    "GetFile",
    "GetMessage",
    "ListEvents",
    "ReadRange",
    "SearchFiles",
    "SearchMessages",
    "SendMessage",
    "WriteRange",
]
