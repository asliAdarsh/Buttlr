# Buttlr — implementation brief for slice agents

## What is being built

**Buttlr** is an AI workforce platform. Users describe an AI employee in natural language; the
platform turns it into a **Buttlr** (name, role, objective, tools, scope, schedule, permissions,
approval policy), deploys it, and runs it on a schedule with a full audit trail.

The product is called **Buttlr**. Each AI employee is also called a **Buttlr** (plural
"Buttlrs"). Never use "agent", "bot", "AI bot", "workflow" or "automation platform" in
user-facing strings, docstrings or API field names. Internal identifiers use `buttlr`.

Positioning: *An AI Workforce Operating System*. Not a chatbot, not an n8n clone, not a prompt
library.

## Hard rules

1. **Read `docs/CONTRACTS.md` first.** It freezes module paths, exported symbols, service methods
   and the full HTTP surface. Implement against it exactly. Do not rename anything.
2. **Read the existing code you depend on before writing.** Particularly:
   - `backend/app/schemas/` (all domain models, enums)
   - `backend/app/core/config.py`, `core/errors.py`, `core/logging.py`
   - `backend/app/database/base.py`, `database/repository.py`
   - `backend/app/container.py` (shows every constructor signature that must match)
   - `backend/app/api/deps.py`
   - `backend/app/runtime/permissions/engine.py`
   - `backend/app/runtime/prompt.py`
3. **Stay inside your assigned files.** Other agents are writing sibling files in the same
   working tree at the same time. Never edit a file you do not own, never edit `app/main.py`,
   `app/api/v1/router.py`, `app/api/errors.py`, `app/api/deps.py`, `app/container.py`,
   `app/schemas/*`, `app/database/base.py`, `app/database/repository.py`,
   `app/runtime/permissions/engine.py`, `app/runtime/prompt.py`, `app/runtime/models/base.py`,
   `app/runtime/models/router.py`, `app/runtime/tools/base.py`, `app/runtime/tools/registry.py`,
   `app/runtime/planner/base.py`, `app/runtime/pubsub.py` — those are owned by the architect.
4. **No placeholders, no mocks, no TODOs, no stubs, no fake fallbacks.** Real implementations.
   If something genuinely cannot be implemented without a credential, implement the real HTTP
   call and fail closed with a clear, actionable error when the credential is absent.
5. **Library-first.** Do not hand-roll OAuth, JWT, HTTP retry, validation, date handling,
   markdown, routing, UI primitives. Use the declared stack. Do not add a dependency that is not
   already in `backend/pyproject.toml` without a strong reason, and if you add one say so.
6. **Do not run `uv sync`, `npm install`, builds, linters or tests.** The architect runs those
   once after all slices land. You MAY run `python -m py_compile <your files>` to catch syntax
   errors (use `uv run python -m py_compile ...` only if `python` is unavailable; do not install
   anything).
7. Python 3.11+: use `from __future__ import annotations`, full type hints, `async def`,
   Pydantic v2 idioms (`model_validate`, `model_dump(mode="python")`, `model_dump(exclude_unset=True)`).
   Always sanity-check generated code by reading it critically; it must actually work.
8. Datetimes are timezone-aware UTC (`app.schemas.common.utcnow()`). Firestore stores `datetime`;
   the memory store stores `datetime` too. Keep datetimes as `datetime` objects in stored dicts.
9. Raise the specific errors from `app.core.errors`, never bare `Exception` for expected failures.
   `NotFoundError`, `ConflictError`, `ValidationError`, `PermissionDeniedError`,
   `UnauthenticatedError`, `IntegrationError`, `ToolExecutionError`, `ModelError`.
10. Log with `app.core.logging.get_logger(__name__)`. Never log secrets, tokens or credentials.

## Environment facts

- Backend has **no Firebase project and no LLM API keys** in this environment. That is why the
  app defaults to `AUTH_MODE=dev` and the in-memory/file store, and why a real deterministic
  fallback planner/provider exists. Both are production code paths, not test scaffolding.
- `GITHUB_TOKEN` in the environment is **invalid** — do not use it. GitHub tools must read the
  credential from `ToolContext.credentials["github"]`, never from `os.environ`.
- Windows, but write POSIX-compatible code and paths; no shell-specific hacks.

## Frontend stack (for frontend slices)

React 18 + Vite + TypeScript + Tailwind CSS v3 + shadcn/ui-style components (Radix primitives +
CVA) + React Router v6 + TanStack Query v5 + a small Zustand store only where genuinely global.
Icons: `lucide-react`. Charts: `recharts`. Toasts: `sonner`. Dates: `date-fns`.

Theme via CSS variables (`--background`, `--foreground`, `--card`, `--muted`, `--primary`,
`--border`, `--danger`, `--success`, `--warning`), light/dark/system. Never hard-code a colour
in a component. Mobile-first: everything must work at 360px width.

## The seventeen-step demo flow that must work end to end

1. Sign in. 2. Create an organization. 3. Create a team. 4. Connect GitHub.
5. Describe an AI employee in natural language. 6. See the generated Buttlr configuration.
7. Define scope. 8. Define permissions. 9. Set a schedule. 10. Test the Buttlr. 11. Deploy it.
12. Watch it execute with live progress. 13. Approve a protected action. 14. See the action
complete. 15. Inspect the audit trail. 16. Change theme/settings. 17. Use it comfortably on
mobile.

Judges must understand the value without a technical explanation.
