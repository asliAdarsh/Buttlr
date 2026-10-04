# Buttlr — demo script

The story: **Acme Technologies → Engineering → PR Guardian**. Everything below is the real
application; nothing is mocked. If a credential is missing the run says so instead of pretending.

## 0. Start

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173
```

Optional, for real repository data — create a GitHub fine-grained personal access token with
read access to one or two repositories. You can paste it in step 1 or connect it later in
**Integrations**. No token? The flow still works end to end; GitHub steps fail closed with a
clear "connect GitHub" message and everything else (permissions, approval, audit) is real.

## 1. Sign in and create the workspace

* **Sign in** with any email (development mode issues a signed session; no cloud account).
* **Load the Acme Technologies demo** — one click. It creates the organization, the
  **Engineering** team, a team lead (`lead@acme.example.com`), and a **PR Guardian** Buttlr built by the
  natural-language builder.
* Or create the organization yourself and continue to the builder.

## 2. Describe the AI employee (the signature moment)

**Buttlrs → Create Buttlr**, then paste:

> Monitor our selected GitHub repositories every morning. Analyse new pull requests for bugs,
> security issues, missing tests and unresolved review comments. Summarise the important
> findings. If a critical issue is found, open a GitHub issue and ask the Engineering Lead for
> approval before creating it.

Point out that no workflow was drawn. The builder returns a complete configuration — name,
role, department, responsibilities, tools, scope, schedule, model, permissions **and** an
approval policy — with its assumptions and open questions listed.

Show refinement in natural language: *"only monitor acme/backend"*, *"run at 8 AM instead"*,
*"always ask me before creating an issue"*.

## 3. Review and narrow scope

* Tools: `github.list_repositories`, `github.list_pull_requests`, `github.get_pull_request`,
  `github.list_pull_request_files`, `github.list_pull_request_comments`, `github.create_issue`.
* Scope: only the repositories you selected.
* Schedule: every day at 09:00, with the timezone.
* Permissions: the Engineering team may **ask**; the Engineering Lead may **approve**; the owner
  has **admin**.
* Approval: `github.create_issue` requires approval.

## 4. Connect GitHub

**Integrations → GitHub**, paste the token, and select the repositories. Deploy needs a
connected integration — that gate is deliberate.

## 5. Deploy, then watch it work

Press **Deploy** with **Create & deploy**. On the Buttlr page choose **Test run** for a dry run
(no writes), or **Run now** for a real one. The progress panel is the live execution stream: each
line is a step that actually happened.

```
✓ Connected to GitHub
✓ Retrieved repositories
✓ Found 5 open pull requests
✓ Analysed PR #182
✓ Found: missing signature verification in payments/webhook.py
⏸ Waiting for approval — create issue
```

## 6. Approve like a manager

**Approvals** shows the pending request with the Buttlr, the action, the target repository, the
reason and the risk level. Approve it (optionally with a note) — the run resumes and creates the
issue. Then show **Reject** on a second request: the run continues and the summary records the
refused action.

Try to approve as the plain member: the platform denies it, because the decision is made from
the stored policy, not from the browser.

## 7. Prove the audit trail

**Activity** shows `organization.created`, `buttlr.created`, `execution.started`,
`tool.executed`, `approval.requested`, `approval.granted`, `execution.completed` with actor,
timestamp, tool, tokens and duration. **Analytics** adds runs, success rate, average duration,
token usage, estimated cost and time saved.

## 8. The product finishes on a phone

Resize to 360px (or open the LAN URL on a phone): the sidebar becomes bottom navigation, the
Buttlr chat is full-width, and approvals are one-tap. Switch **Settings → Appearance** between
light, dark, system and the accent colours.

## What is deliberately not here

* Marketplace, billing, SSO, multi-Buttlr orchestration, vector RAG — the roadmap, not the demo.
* A Buttlr never widens its own scope, and no tool runs without a permission decision from the
  server.
