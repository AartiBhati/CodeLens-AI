from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "supersecret123"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    return resp.json()["access_token"]


async def _setup_repo(client, headers):
    project_id = (await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"]
    repo = await client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers=headers,
    )
    return repo.json()["id"]


def _fake_chunks():
    return [
        {
            "score": 0.9,
            "text": "def foo(): return 42",
            "file_path": "app/foo.py",
            "start_line": 1,
            "end_line": 2,
            "function_name": "foo",
            "class_name": None,
        }
    ]


async def _fake_stream_tokens(*_args, **_kwargs):
    class Chunk:
        content = "The answer is 42."
    yield Chunk()


async def test_ask_persists_user_and_assistant_messages(app_client):
    token = await _register_and_login(app_client, "chatuser@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    repo_id = await _setup_repo(app_client, headers)

    with patch("app.rag.chain.retrieve", return_value=_fake_chunks()), \
         patch("app.rag.chain.get_chat_model") as mock_model_factory:
        mock_model_factory.return_value.astream = _fake_stream_tokens

        resp = await app_client.post(
            "/api/v1/chat/ask",
            json={"repository_id": repo_id, "question": "what does foo do?"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.text
        assert "token" in body
        assert "done" in body

    # Extract conversation_id from the streamed "done" event to check persistence.
    import json
    done_line = [line for line in body.splitlines() if '"type": "done"' in line][0]
    payload = json.loads(done_line.removeprefix("data: "))
    conversation_id = payload["conversation_id"]

    conv_resp = await app_client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert conv_resp.status_code == 200
    messages = conv_resp.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "42" in messages[1]["content"]


async def test_ask_requires_repository_ownership(app_client):
    token_a = await _register_and_login(app_client, "chata@example.com")
    token_b = await _register_and_login(app_client, "chatb@example.com")
    repo_id = await _setup_repo(app_client, {"Authorization": f"Bearer {token_a}"})

    resp = await app_client.post(
        "/api/v1/chat/ask",
        json={"repository_id": repo_id, "question": "anything"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


async def test_ask_enforces_rate_limit(app_client):
    token = await _register_and_login(app_client, "ratelimited@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    repo_id = await _setup_repo(app_client, headers)

    with patch("app.rag.chain.retrieve", return_value=_fake_chunks()), \
         patch("app.rag.chain.get_chat_model") as mock_model_factory, \
         patch("app.services.rate_limiter.settings.RATE_LIMIT_REQUESTS_PER_MINUTE", 1):
        mock_model_factory.return_value.astream = _fake_stream_tokens

        first = await app_client.post(
            "/api/v1/chat/ask", json={"repository_id": repo_id, "question": "q1"}, headers=headers
        )
        assert first.status_code == 200

        second = await app_client.post(
            "/api/v1/chat/ask", json={"repository_id": repo_id, "question": "q2"}, headers=headers
        )
        assert second.status_code == 429
        assert "Retry-After" in second.headers
