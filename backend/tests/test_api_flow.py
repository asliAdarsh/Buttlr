"""HTTP surface: identity, organizations, teams, Buttler configuration and access control."""

from __future__ import annotations

from tests.conftest import auth


def create_org(client, token: str, name: str = "Acme Technologies") -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={"name": name, "description": "Test org"},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health_and_meta_are_public(client) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    meta = client.get("/api/v1/meta/config")
    assert meta.status_code == 200
    body = meta.json()
    assert body["app_name"] == "Buttlr"
    assert body["dev_login_enabled"] is True
    assert "heuristic" in body["providers"]


def test_requests_without_a_token_are_rejected(client) -> None:
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/organizations").status_code == 401
    bad = client.get("/api/v1/users/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401


def test_dev_login_provisions_a_user_and_session(client) -> None:
    tokens = client.post("/api/v1/auth/dev/login", json={"email": "alice@example.com"}).json()
    session = client.get("/api/v1/auth/session", headers=auth(tokens["access_token"]))
    assert session.status_code == 200
    body = session.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["organizations"] == []


def test_organization_creation_makes_the_creator_an_owner(client) -> None:
    tokens = client.post("/api/v1/auth/dev/login", json={"email": "owner@example.com"}).json()
    token = tokens["access_token"]
    organization = create_org(client, token)

    listing = client.get("/api/v1/organizations", headers=auth(token)).json()
    assert len(listing) == 1
    assert listing[0]["organization"]["id"] == organization["id"]
    assert listing[0]["role"] == "owner"
    assert listing[0]["member_count"] == 1

    members = client.get(
        f"/api/v1/organizations/{organization['id']}/members", headers=auth(token)
    ).json()
    assert members[0]["role"] == "owner"
    assert members[0]["user"]["email"] == "owner@example.com"


def test_a_non_member_cannot_read_an_organization(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner2@example.com"}).json()
    outsider = client.post("/api/v1/auth/dev/login", json={"email": "mallory@evil.example.com"}).json()
    organization = create_org(client, owner["access_token"], "Private Corp")

    forbidden = client.get(
        f"/api/v1/organizations/{organization['id']}", headers=auth(outsider["access_token"])
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"


def test_teams_and_invites_round_trip(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner3@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Team Corp")

    team = client.post(
        f"/api/v1/organizations/{organization['id']}/teams",
        json={"name": "Engineering", "emoji": "⚙️", "color": "violet"},
        headers=auth(token),
    )
    assert team.status_code == 201, team.text

    invite = client.post(
        f"/api/v1/organizations/{organization['id']}/members",
        json={"email": "lead@example.com", "role": "admin", "team_ids": [team.json()["id"]]},
        headers=auth(token),
    )
    assert invite.status_code == 201, invite.text
    assert invite.json()["role"] == "admin"
    assert invite.json()["user"]["email"] == "lead@example.com"

    members = client.get(
        f"/api/v1/organizations/{organization['id']}/members", headers=auth(token)
    ).json()
    assert len(members) == 2
    assert any(member["team_ids"] for member in members)

    lead_login = client.post("/api/v1/auth/dev/login", json={"email": "lead@example.com"}).json()
    lead_session = client.get("/api/v1/auth/session", headers=auth(lead_login["access_token"])).json()
    assert lead_session["organizations"][0]["id"] == organization["id"]


def test_buttlr_permissions_are_enforced_from_the_store_not_the_request(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner4@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Perm Corp")

    buttlr = client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs",
        json={"name": "PR Guardian", "role": "AI Pull Request Assistant", "tools": []},
        headers=auth(token),
    )
    assert buttlr.status_code == 201, buttlr.text
    buttlr_id = buttlr.json()["id"]

    # The owner can read it (owner has the admin floor).
    assert (
        client.get(
            f"/api/v1/organizations/{organization['id']}/buttlrs/{buttlr_id}", headers=auth(token)
        ).status_code
        == 200
    )

    # Invite a plain member with no grant: they must not be able to read the Buttlr.
    client.post(
        f"/api/v1/organizations/{organization['id']}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=auth(token),
    )
    member = client.post("/api/v1/auth/dev/login", json={"email": "member@example.com"}).json()
    denied = client.get(
        f"/api/v1/organizations/{organization['id']}/buttlrs/{buttlr_id}",
        headers=auth(member["access_token"]),
    )
    assert denied.status_code == 403, denied.text

    # The listing must not leak it either, and the audit trail is admin-only.
    listed = client.get(
        f"/api/v1/organizations/{organization['id']}/buttlrs",
        headers=auth(member["access_token"]),
    )
    assert listed.status_code == 200
    assert listed.json() == []

    audit = client.get(
        f"/api/v1/organizations/{organization['id']}/audit", headers=auth(member["access_token"])
    )
    assert audit.status_code == 403

    executions = client.get(
        f"/api/v1/organizations/{organization['id']}/executions",
        headers=auth(member["access_token"]),
    )
    assert executions.status_code == 200


def test_buttlr_cannot_be_created_with_an_unknown_tool(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner5@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Tool Corp")

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs",
        json={"name": "Broken", "tools": ["github.teleport"]},
        headers=auth(token),
    )
    assert response.status_code == 422
    assert "github.teleport" in response.text


def test_deploy_requires_a_connected_integration(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner6@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Deploy Corp")
    created = client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs",
        json={
            "name": "PR Guardian",
            "tools": ["github.list_pull_requests"],
            "integrations": ["github"],
        },
        headers=auth(token),
    )
    assert created.status_code == 201, created.text

    deployed = client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs/{created.json()['id']}/deploy",
        headers=auth(token),
    )
    assert deployed.status_code == 422
    assert "github" in deployed.json()["error"]["message"].lower()


def test_natural_language_builder_produces_a_usable_configuration(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner7@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Builder Corp")

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs/draft",
        json={
            "prompt": (
                "Monitor our selected GitHub repositories every morning. Analyse new pull "
                "requests for bugs, security issues and missing tests. Summarise the important "
                "findings. If a critical issue is found, open a GitHub issue and ask me for "
                "approval before creating it."
            ),
            "organization_id": organization["id"],
        },
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["name"]
    assert "github.list_pull_requests" in body["draft"]["tools"]
    assert body["draft"]["schedule"]["enabled"] is True
    assert body["draft"]["schedule"]["kind"] == "daily"
    assert body["draft"]["schedule"]["at"] == "09:00"
    rules = {rule["tool"]: rule["mode"] for rule in body["draft"]["approval_policy"]["rules"]}
    assert rules.get("github.create_issue") == "ask"


def test_audit_log_records_organization_and_buttlr_actions(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner8@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Audit Corp")
    client.post(
        f"/api/v1/organizations/{organization['id']}/buttlrs",
        json={"name": "Recorder", "tools": []},
        headers=auth(token),
    )
    audit = client.get(f"/api/v1/organizations/{organization['id']}/audit", headers=auth(token))
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()["items"]}
    assert "organization.created" in actions
    assert "buttlr.created" in actions


def test_notifications_start_empty_and_approval_stats_are_zero(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner9@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Quiet Corp")

    notifications = client.get(
        f"/api/v1/organizations/{organization['id']}/notifications", headers=auth(token)
    )
    assert notifications.status_code == 200

    stats = client.get(
        f"/api/v1/organizations/{organization['id']}/approvals/stats", headers=auth(token)
    )
    assert stats.status_code == 200
    assert stats.json() == {"pending": 0, "approved": 0, "rejected": 0, "expired": 0}


def test_dashboard_and_analytics_are_scoped_to_the_organization(client) -> None:
    owner = client.post("/api/v1/auth/dev/login", json={"email": "owner10@example.com"}).json()
    token = owner["access_token"]
    organization = create_org(client, token, "Insight Corp")
    dashboard = client.get(
        f"/api/v1/organizations/{organization['id']}/dashboard", headers=auth(token)
    )
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["organization"]["id"] == organization["id"]
    assert dashboard.json()["buttlrs_total"] == 0

    analytics = client.get(
        f"/api/v1/organizations/{organization['id']}/analytics/overview?days=7",
        headers=auth(token),
    )
    assert analytics.status_code == 200
    assert analytics.json()["executions_total"] == 0


def test_demo_seed_is_idempotent_and_builds_the_story(client) -> None:
    first = client.post("/api/v1/dev/seed", json={})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True
    assert body["github_connected"] is False, "no token was supplied, so nothing is faked"
    assert body["deployed"] is False

    second = client.post("/api/v1/dev/seed", json={})
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["organization_id"] == body["organization_id"]
