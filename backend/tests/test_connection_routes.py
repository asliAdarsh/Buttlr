"""HTTP surface for connections: who may connect, and what the API may return."""

from __future__ import annotations

from tests.conftest import auth


def session(client, email: str) -> tuple[str, str]:
    """Sign in and return (token, user_id)."""
    response = client.post("/api/v1/auth/dev/login", json={"email": email})
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]["id"]


def organization_with_member(client) -> tuple[str, str, str, str, str]:
    """Owner token, member token, org id, owner id, member id."""
    owner_token, owner_id = session(client, "owner@connections.example.com")
    created = client.post(
        "/api/v1/organizations",
        json={"name": "Connections Inc"},
        headers=auth(owner_token),
    )
    assert created.status_code == 201, created.text
    organization_id = created.json()["id"]

    invited = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json={"email": "member@connections.example.com", "role": "member"},
        headers=auth(owner_token),
    )
    assert invited.status_code == 201, invited.text
    member_token, member_id = session(client, "member@connections.example.com")

    # Give the member a Buttler they can operate, which also exercises the grant path.
    client.post(
        f"/api/v1/organizations/{organization_id}/buttlrs",
        json={"name": "Team Bot", "tools": []},
        headers=auth(owner_token),
    )
    return owner_token, member_token, organization_id, owner_id, member_id


def test_a_member_cannot_connect_a_shared_account(client) -> None:
    _, member_token, organization_id, _, _ = organization_with_member(client)
    response = client.post(
        f"/api/v1/organizations/{organization_id}/integrations/token",
        json={
            "provider": "github",
            "token": "ghp_member_token_value",
            "scope": "organization",
        },
        headers=auth(member_token),
    )
    assert response.status_code == 403
    assert "shared account" in response.json()["error"]["message"]


def test_the_default_scope_is_the_person_not_the_workspace(client) -> None:
    """Omitting the scope must never create a workspace-wide connection by accident."""
    from app.schemas.integration import IntegrationConnectToken

    assert IntegrationConnectToken(provider="github", token="ghp_token_value").scope.value == (
        "personal"
    )


def test_connection_listings_never_expose_a_secret(client, container) -> None:
    owner_token, _, organization_id, owner_id, _ = organization_with_member(client)

    # Store one personal connection directly: the provider probe needs a real account.
    import asyncio

    from app.core.crypto import seal_credentials
    from app.schemas.common import utcnow

    asyncio.run(
        container.store.set(
            f"organizations/{organization_id}/integrations",
            f"github:{owner_id}",
            {
                "id": f"github:{owner_id}",
                "organization_id": organization_id,
                "provider": "github",
                "display_name": "GitHub",
                "scope": "personal",
                "owner_id": owner_id,
                "owner_name": "Owner",
                "status": "connected",
                "account": "octocat",
                "credentials": seal_credentials({"token": "ghp_owner_token_value"}),
                "created_at": utcnow(),
                "updated_at": utcnow(),
            },
            merge=False,
        )
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/integrations", headers=auth(owner_token)
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["scope"] == "personal"
    assert rows[0]["owner_name"] == "Owner"
    assert "credentials" not in rows[0]
    assert "ghp_owner_token_value" not in response.text


def test_a_failed_oauth_callback_returns_to_the_app_not_a_json_page(client, container) -> None:
    """The user arrives here in a browser: a failure must land back in the UI, readable."""
    from app.integrations.oauth import sign_state
    from app.schemas.enums import IntegrationProvider

    owner_token, _, organization_id, _, _ = organization_with_member(client)
    # A valid, signed state — but for the wrong provider, which is what a stale tab looks like.
    state = sign_state(
        IntegrationProvider.GITHUB,
        organization_id,
        "http://localhost:8000/api/v1/integrations/oauth/google/callback",
        container.settings.dev_auth_secret,
        user_id="someone",
    )
    response = client.get(
        f"/api/v1/integrations/oauth/google/callback?code=abc&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith("http://localhost:5173/integrations?oauth_error="), location
    assert "different%20service" in location
    assert owner_token  # the member fixture was created and is irrelevant to this path


def test_a_workspace_can_register_its_own_oauth_app_over_http(client) -> None:
    owner_token, member_token, organization_id, _, _ = organization_with_member(client)

    empty = client.get(
        f"/api/v1/organizations/{organization_id}/integrations/oauth-clients",
        headers=auth(owner_token),
    )
    assert empty.status_code == 200
    assert {row["provider"] for row in empty.json()} == {"github", "google"}
    assert all(row["configured"] is False for row in empty.json())

    forbidden = client.put(
        f"/api/v1/organizations/{organization_id}/integrations/oauth-clients/github",
        json={"client_id": "Iv1.member", "client_secret": "nope"},
        headers=auth(member_token),
    )
    assert forbidden.status_code == 403

    saved = client.put(
        f"/api/v1/organizations/{organization_id}/integrations/oauth-clients/github",
        json={"client_id": "Iv1.workspaceapp", "client_secret": "workspace-secret"},
        headers=auth(owner_token),
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["configured"] is True
    assert body["source"] == "workspace"
    assert body["has_secret"] is True
    assert "workspace-secret" not in saved.text
    assert "client_secret" not in body

    # With the workspace's app in place, sign-in works with nothing in the environment.
    started = client.get(
        f"/api/v1/organizations/{organization_id}/integrations/github/oauth/start"
        "?scope=personal",
        headers=auth(member_token),
    )
    assert started.status_code == 200, started.text
    assert "client_id=Iv1.workspaceapp" in started.json()["authorization_url"]

    # A member may not start a workspace-wide sign-in.
    refused = client.get(
        f"/api/v1/organizations/{organization_id}/integrations/github/oauth/start"
        "?scope=organization",
        headers=auth(member_token),
    )
    assert refused.status_code == 403


def test_oauth_apps_are_only_for_oauth_providers(client) -> None:
    owner_token, _, organization_id, _, _ = organization_with_member(client)
    response = client.put(
        f"/api/v1/organizations/{organization_id}/integrations/oauth-clients/jira",
        json={"client_id": "Iv1.jira", "client_secret": "s"},
        headers=auth(owner_token),
    )
    assert response.status_code == 422
    assert "token" in response.json()["error"]["message"].lower()


def test_oauth_start_explains_what_to_configure_when_nothing_is_set_up(client) -> None:
    _, member_token, organization_id, _, _ = organization_with_member(client)
    response = client.get(
        f"/api/v1/organizations/{organization_id}/integrations/google/oauth/start",
        headers=auth(member_token),
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "OAuth app" in message


def test_only_the_owner_of_a_connection_may_disconnect_it(client, container) -> None:
    owner_token, member_token, organization_id, owner_id, member_id = organization_with_member(
        client
    )
    import asyncio

    from app.core.crypto import seal_credentials
    from app.schemas.common import utcnow

    def document(owner: str) -> dict:
        return {
            "id": f"github:{owner}",
            "organization_id": organization_id,
            "provider": "github",
            "display_name": "GitHub",
            "scope": "personal",
            "owner_id": owner,
            "owner_name": owner,
            "status": "connected",
            "account": "octocat",
            "credentials": seal_credentials({"token": "ghp_personal_token_value"}),
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }

    asyncio.run(
        container.store.set(
            f"organizations/{organization_id}/integrations",
            f"github:{owner_id}",
            document(owner_id),
            merge=False,
        )
    )

    # The member may not touch the owner's connection.
    refused = client.delete(
        f"/api/v1/organizations/{organization_id}/integrations/github:{owner_id}",
        headers=auth(member_token),
    )
    assert refused.status_code == 403

    removed = client.delete(
        f"/api/v1/organizations/{organization_id}/integrations/github:{owner_id}",
        headers=auth(owner_token),
    )
    assert removed.status_code == 204
    assert member_id  # the member exists and was simply not the owner
