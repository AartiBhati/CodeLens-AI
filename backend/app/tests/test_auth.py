import pytest

pytestmark = pytest.mark.asyncio


async def test_register_and_login(app_client):
    resp = await app_client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "supersecret123", "full_name": "Dev User"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "dev@example.com"
    assert "hashed_password" not in body  # never leak the hash

    resp = await app_client.post(
        "/api/v1/auth/login", json={"email": "dev@example.com", "password": "supersecret123"}
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens


async def test_duplicate_registration_rejected(app_client):
    payload = {"email": "dup@example.com", "password": "supersecret123"}
    first = await app_client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await app_client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_wrong_password_rejected(app_client):
    await app_client.post(
        "/api/v1/auth/register", json={"email": "wrongpw@example.com", "password": "correcthorse123"}
    )
    resp = await app_client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "nope"}
    )
    assert resp.status_code == 401


async def test_protected_endpoint_requires_token(app_client):
    resp = await app_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(app_client):
    await app_client.post(
        "/api/v1/auth/register", json={"email": "me@example.com", "password": "supersecret123"}
    )
    login = await app_client.post(
        "/api/v1/auth/login", json={"email": "me@example.com", "password": "supersecret123"}
    )
    token = login.json()["access_token"]

    resp = await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


async def test_logout_invalidates_token(app_client):
    await app_client.post(
        "/api/v1/auth/register", json={"email": "logout@example.com", "password": "supersecret123"}
    )
    login = await app_client.post(
        "/api/v1/auth/login", json={"email": "logout@example.com", "password": "supersecret123"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert (await app_client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    logout_resp = await app_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 204

    # Same token must now be rejected -- this is the blacklist invalidation strategy.
    assert (await app_client.get("/api/v1/auth/me", headers=headers)).status_code == 401
