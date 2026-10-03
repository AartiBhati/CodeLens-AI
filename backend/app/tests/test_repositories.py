import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "supersecret123"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    return resp.json()["access_token"]


async def test_create_and_list_projects(app_client):
    token = await _register_and_login(app_client, "owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await app_client.post(
        "/api/v1/projects", json={"name": "My Project", "description": "desc"}, headers=headers
    )
    assert resp.status_code == 201

    resp = await app_client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "My Project"


async def test_user_cannot_access_other_users_project(app_client):
    token_a = await _register_and_login(app_client, "alice@example.com")
    token_b = await _register_and_login(app_client, "bob@example.com")

    create_resp = await app_client.post(
        "/api/v1/projects",
        json={"name": "Alice's project"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    project_id = create_resp.json()["id"]

    # Bob tries to fetch Alice's project directly by ID.
    resp = await app_client.get(
        f"/api/v1/projects/{project_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404  # not "403" -- avoids leaking existence


async def test_connect_repository_validates_github_url(app_client):
    token = await _register_and_login(app_client, "repo-owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_id = (
        await app_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    ).json()["id"]

    bad = await app_client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json={"github_url": "not-a-github-url"},
        headers=headers,
    )
    assert bad.status_code == 422

    good = await app_client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json={"github_url": "https://github.com/octocat/Hello-World", "branch": "master"},
        headers=headers,
    )
    assert good.status_code == 201
    assert good.json()["index_status"] == "pending"


async def test_trigger_indexing_publishes_kafka_event_and_returns_immediately(app_client):
    token = await _register_and_login(app_client, "indexer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    project_id = (
        await app_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    ).json()["id"]
    repo_id = (
        await app_client.post(
            f"/api/v1/projects/{project_id}/repositories",
            json={"github_url": "https://github.com/octocat/Hello-World"},
            headers=headers,
        )
    ).json()["id"]

    resp = await app_client.post(f"/api/v1/repositories/{repo_id}/index", headers=headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "job_id" in body

    # The API must not block on indexing -- it publishes an event instead.
    app_client.mock_publish_event.assert_called_once()
    call_kwargs = app_client.mock_publish_event.call_args
    assert call_kwargs.args[0] == "repository.index.requested"


async def test_repository_ownership_enforced_on_index_trigger(app_client):
    token_a = await _register_and_login(app_client, "own1@example.com")
    token_b = await _register_and_login(app_client, "own2@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    project_id = (
        await app_client.post("/api/v1/projects", json={"name": "P"}, headers=headers_a)
    ).json()["id"]
    repo_id = (
        await app_client.post(
            f"/api/v1/projects/{project_id}/repositories",
            json={"github_url": "https://github.com/octocat/Hello-World"},
            headers=headers_a,
        )
    ).json()["id"]

    resp = await app_client.post(
        f"/api/v1/repositories/{repo_id}/index", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404
