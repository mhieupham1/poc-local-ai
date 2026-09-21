from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import httpx
import pytest


def _gateway_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.gateway.app")
    except ModuleNotFoundError as exc:
        pytest.fail(f"gateway app is not implemented: {exc}")


def _settings(module: object, token_file: Path, **overrides: object) -> object:
    values: dict[str, object] = {
        "auth_mode": "token",
        "token_file": token_file,
        "llm_url": "http://llm:8000",
        "embedding_url": "http://embedding:80",
        "request_timeout_seconds": 5,
        "max_body_bytes": 1024,
        "max_concurrency": 2,
        "queue_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return module.GatewaySettings(**values)  # type: ignore[attr-defined]


def _token_file(tmp_path: Path) -> Path:
    path = tmp_path / "gateway-token"
    path.write_text("s" * 48)
    path.chmod(0o600)
    return path


def test_gateway_rejects_missing_auth_before_contacting_upstream(tmp_path: Path) -> None:
    gateway = _gateway_module()
    upstream_calls = 0

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200, json={"ok": True})

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(gateway, _token_file(tmp_path)),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            return await client.post("/v1/chat/completions", json={"messages": []})

    response = asyncio.run(call())

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}
    assert upstream_calls == 0


def test_gateway_routes_chat_and_embedding_without_forwarding_credential(tmp_path: Path) -> None:
    gateway = _gateway_module()
    calls: list[tuple[str, str | None, dict[str, object]]] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(
            (
                str(request.url),
                request.headers.get("authorization"),
                json.loads(request.content),
            )
        )
        if request.url.host == "llm":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b'data: {"choices":[{"delta":{"content":"xin"}}]}\n\ndata: [DONE]\n\n',
            )
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2], "index": 0}]})

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(gateway, _token_file(tmp_path)),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            headers = {"Authorization": f"Bearer {'s' * 48}"}
            chat = await client.post(
                "/v1/chat/completions",
                headers=headers,
                json={"model": "local-vision-language", "messages": [], "stream": True},
            )
            embedding = await client.post(
                "/v1/embeddings",
                headers=headers,
                json={"model": "BAAI/bge-m3", "input": ["xin chào"]},
            )
            return chat, embedding

    chat, embedding = asyncio.run(call())

    assert chat.status_code == 200
    assert chat.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in chat.text
    assert embedding.status_code == 200
    assert embedding.json()["data"][0]["index"] == 0
    assert [call[0] for call in calls] == [
        "http://llm:8000/v1/chat/completions",
        "http://embedding/v1/embeddings",
    ]
    assert [call[1] for call in calls] == [None, None]


def test_gateway_rejects_oversized_body_without_forwarding(tmp_path: Path) -> None:
    gateway = _gateway_module()
    upstream_calls = 0

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200)

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(gateway, _token_file(tmp_path), max_body_bytes=16),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            return await client.post(
                "/v1/embeddings",
                headers={"Authorization": f"Bearer {'s' * 48}"},
                content=b"x" * 17,
            )

    response = asyncio.run(call())

    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}
    assert upstream_calls == 0


def test_gateway_settings_reject_external_model_upstream(tmp_path: Path) -> None:
    gateway = _gateway_module()

    with pytest.raises(ValueError, match="private service name or loopback"):
        _settings(gateway, _token_file(tmp_path), llm_url="https://api.example.com")


def test_gateway_rejects_unapproved_remote_media_url(tmp_path: Path) -> None:
    gateway = _gateway_module()
    upstream_calls = 0

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200)

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(gateway, _token_file(tmp_path)),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            return await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {'s' * 48}"},
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": "http://169.254.169.254/latest/meta-data"},
                                }
                            ],
                        }
                    ]
                },
            )

    response = asyncio.run(call())

    assert response.status_code == 400
    assert response.json() == {"detail": "remote media URL is not allowed"}
    assert upstream_calls == 0


def test_gateway_releases_slot_after_unexpected_upstream_error(tmp_path: Path) -> None:
    gateway = _gateway_module()
    calls = 0

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("unexpected transport failure")
        return httpx.Response(200, json={"data": []})

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(
            gateway,
            _token_file(tmp_path),
            max_concurrency=1,
            queue_timeout_seconds=0.01,
        ),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            headers = {"Authorization": f"Bearer {'s' * 48}"}
            with pytest.raises(RuntimeError, match="unexpected transport failure"):
                await client.post("/v1/embeddings", headers=headers, json={"input": ["one"]})
            return await client.post("/v1/embeddings", headers=headers, json={"input": ["two"]})

    response = asyncio.run(call())

    assert response.status_code == 200
    assert calls == 2


def test_gateway_releases_slot_when_upstream_stream_fails(tmp_path: Path) -> None:
    gateway = _gateway_module()
    calls = 0

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):  # type: ignore[no-untyped-def]
            yield b"first"
            raise OSError("stream disconnected")

    def upstream(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, stream=BrokenStream())
        return httpx.Response(200, json={"data": []})

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(
            gateway,
            _token_file(tmp_path),
            max_concurrency=1,
            queue_timeout_seconds=0.01,
        ),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            headers = {"Authorization": f"Bearer {'s' * 48}"}
            with pytest.raises(OSError, match="stream disconnected"):
                await client.post("/v1/embeddings", headers=headers, json={"input": ["one"]})
            return await client.post("/v1/embeddings", headers=headers, json={"input": ["two"]})

    response = asyncio.run(call())

    assert response.status_code == 200
    assert calls == 2


def test_readyz_checks_both_model_upstreams(tmp_path: Path) -> None:
    gateway = _gateway_module()

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.url.host == "llm" else 503)

    app = gateway.create_app(  # type: ignore[attr-defined]
        _settings(gateway, _token_file(tmp_path)),
        upstream_transport=httpx.MockTransport(upstream),
    )

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway"
        ) as client:
            return await client.get("/readyz")

    response = asyncio.run(call())

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "upstreams": {"embedding": False, "llm": True},
    }
