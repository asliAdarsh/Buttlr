# Buttlr

**An AI Workforce Operating System.**

Buttlr lets an organization create AI employees — called **Buttlrs** — by describing them in
natural language, giving them scoped access to real tools (GitHub, Jira, Gmail, Drive, Sheets),
deciding what they are allowed to do on their own, and supervising the rest through human approval.

> Describe → Configure → Permission → Deploy → Execute → Approve → Log

---

## Why it is not another workflow builder

You do not drag nodes. You write:

> "Monitor our selected GitHub repositories every morning. Analyze new pull requests for bugs,
> security issues, missing tests and unresolved review comments. Summarize the important findings.
> If a critical issue is found, prepare a Jira ticket and ask the Engineering Lead for approval
> before creating it."

Buttlr turns that into a reviewable configuration — scope, tools, schedule, permissions and
approval policy — and then runs it on a schedule with a complete audit trail.

---

## Architecture

```
React + Vite + TS (Vercel)
        │  REST + SSE
        ▼
FastAPI modular monolith (Render)
        │
        ├── Domain services      organizations · teams · buttlrs · integrations · approvals · audit
        ├── Buttlr Runtime       model router → planner → permission engine → tools → observation
        ├── Scheduler            APScheduler (cron / interval, per-Buttlr timezone)
        └── Store                Firestore (prod) · in-memory + JSON (dev/demo)
```

The runtime is a loop, not a chain of nodes:

```
Intent → Planner → Permission Engine → Tool Execution → Observation → Planner → … → Completion
```

Every tool call passes through the permission engine **before** it executes. The engine returns
`ALLOW`, `DENY` or `REQUEST_APPROVAL` based on the policy stored server-side — never on anything
the browser sends.

---

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/app/core` | config, logging, errors, security, request context |
| `backend/app/database` | `Store` contract, Firestore + in-memory implementations |
| `backend/app/auth` | Firebase ID-token verification, dev issuer, user provisioning |
| `backend/app/schemas` | Pydantic domain models (single source of truth for the API) |
| `backend/app/api/v1` | HTTP routers |
| `backend/app/services` | domain services (organizations, teams, buttlrs, approvals, audit) |
| `backend/app/runtime` | models · planner · executor · permissions · tools · memory |
| `backend/app/integrations` | OAuth + provider clients |
| `backend/app/scheduler` | scheduled + event-driven execution |
| `frontend/src` | React application |

---

## Branch model

| Branch | Purpose | Deploys to |
| --- | --- | --- |
| `main` | production, always deployable | Vercel / Render **production** |
| `dev` | integration, staging | Vercel / Render **staging** |
| `feat/*` | one slice of work, merged into `dev` with `--no-ff` | — |

Flow: `feat/*` → `dev` → `main`.

---

## Local development

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Runs with `AUTH_MODE=dev` and the in-memory/file store by default, so no cloud account is needed.
Interactive API docs: <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

<http://localhost:5173> — the dev server proxies `/api` to the backend.

### Demo data

```bash
curl -X POST http://localhost:8000/api/v1/dev/seed
```

Creates **Acme Technologies**, the Engineering team and the `PR Guardian` Buttlr. Pass a GitHub
token in the body (`{"github_token": "github_pat_…"}`) and it also connects GitHub and deploys the
Buttlr; without one it stays a draft and says so, because Buttlr never pretends a credential works.
Pass `{"reset": true}` to rebuild it.

---

## Connections

Everything a Buttlr touches is connected **in the application**, under **Integrations** — never
by editing `.env`:

* **Anyone** connects their own GitHub, Jira or Google account. Buttlrs they run use *their*
  account, so a run can never reach more than the person behind it.
* An **owner or admin** can additionally connect one shared account for the workspace, used
  when the person running a Buttlr has not connected their own.
* Resolution per provider is: the account of the person running it → the account of the person
  who owns the Buttlr → the workspace's shared account. If none exists, the tool fails closed
  with a message naming the fix.
* Credentials are encrypted at rest with `ENCRYPTION_KEY` and never returned by the API — not
  even to an administrator. Disconnecting deletes them.

Sign-in flows (Google, or GitHub OAuth instead of a personal access token) need an OAuth app.
A workspace can register **its own** under *Integrations → OAuth apps*; the deployment-wide
`GITHUB_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_ID` pair is only a fallback for workspaces that
have not registered one. Neither is required to use Buttlr.

---

## Configuration

All settings come from environment variables (see `backend/.env.example` and
`frontend/.env.example`). Nothing requires a cloud account to boot.

| Variable | Effect |
| --- | --- |
| `AUTH_MODE` | `dev` (self-issued JWTs) or `firebase` (verify Firebase ID tokens) |
| `STORE_BACKEND` | `auto` \| `firestore` \| `memory` |
| `ENCRYPTION_KEY` | at-rest encryption for connection credentials |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | enable a cloud model provider |
| `OLLAMA_BASE_URL` | enable a local model provider |
| `GITHUB_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_ID` | optional deployment-wide OAuth apps |

No provider credential — GitHub token, Jira API token, Google refresh token — is ever read from
the environment.

When no model credentials are present the runtime uses the built-in **deterministic planner**
(`heuristic` provider). It is a real rule-based planner — the product works end to end offline,
and the same code path is used by the test-suite.

---

## Tests

```bash
cd backend && uv run pytest        # domain, permission, approval and runtime tests
cd frontend && npm run build       # type-check + production build
```

---

## Deployment

* `render.yaml` — backend web services for staging (`dev`) and production (`main`).
* `frontend/vercel.json` — SPA rewrites; set `VITE_API_BASE_URL` per environment.
* `docker-compose.yml` — full stack locally, including an optional Ollama container.
