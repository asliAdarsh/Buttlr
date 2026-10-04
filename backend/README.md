# Buttlr backend

FastAPI modular monolith: domain services, the Buttlr runtime (planner → permission engine →
tools), integrations, scheduling and the audit trail.

See the repository root `README.md` and `docs/` for architecture, contracts and the demo flow.

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Boots with `AUTH_MODE=dev` and the in-memory/file store, so no cloud account is required.
