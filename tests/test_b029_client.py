from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from local_ai_lab.poc_b029.client import B029GatewayClient, GatewayClientError


def _credential_file(tmp_path: Path) -> Path:
    path = tmp_path / "gateway-token"
    path.write_text("x" * 32, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_extract_record_sends_structured_vision_request_with_file_credential(
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["authorization"] = request.headers["authorization"]
        observed["request_id"] = request.headers["x-request-id"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": request.headers["x-request-id"]},
            json={
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "work_date": "2026-09-21",
                                    "work_order": "WO-001",
                                    "process": "PRESS",
                                    "item_code": "AB-01",
                                    "actual_quantity": 120,
                                    "defect_quantity": 2,
                                }
                            )
                        }
                    }
                ],
            },
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(
            base_url="https://gateway.example", transport=httpx.MockTransport(handler)
        ) as http_client:
            client = B029GatewayClient.from_credential_file(http_client, _credential_file(tmp_path))
            response = await client.extract_record(
                image_data_url="data:image/png;base64,c2FmZS1maXh0dXJl"
            )

        assert response.record.work_order == "WO-001"
        assert response.request_id == observed["request_id"]
        assert "data:image" not in str(response.model_dump())

    asyncio.run(exercise())

    payload = observed["payload"]
    assert observed["path"] == "/v1/chat/completions"
    assert observed["authorization"] == f"Bearer {'x' * 32}"
    assert isinstance(observed["request_id"], str)
    assert isinstance(payload, dict)
    assert payload["model"] == "local-vision-language"
    assert payload["stream"] is False
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png")


def test_gateway_client_redacts_upstream_and_malformed_response_errors(tmp_path: Path) -> None:
    async def exercise() -> None:
        malformed = httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"model": "vision", "choices": [{"message": {"content": "not json"}}]},
            )
        )
        async with httpx.AsyncClient(
            base_url="https://gateway.example", transport=malformed
        ) as http_client:
            client = B029GatewayClient.from_credential_file(http_client, _credential_file(tmp_path))
            with pytest.raises(GatewayClientError, match="structured JSON"):
                await client.extract_record(image_data_url="data:image/png;base64,c2FmZQ==")

        failed = httpx.MockTransport(lambda _request: httpx.Response(503, text="sensitive body"))
        async with httpx.AsyncClient(
            base_url="https://gateway.example", transport=failed
        ) as http_client:
            client = B029GatewayClient.from_credential_file(http_client, _credential_file(tmp_path))
            with pytest.raises(GatewayClientError, match="HTTP 503") as error:
                await client.embed_texts(("query", "rule"))
            assert "sensitive body" not in str(error.value)

    asyncio.run(exercise())


def test_embed_texts_returns_only_vectors_and_safe_metadata(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert json.loads(request.content)["input"] == ["query", "rule"]
        return httpx.Response(
            200,
            headers={"x-request-id": request.headers["x-request-id"]},
            json={
                "model": "BAAI/bge-m3",
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0]},
                ],
            },
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(
            base_url="https://gateway.example", transport=httpx.MockTransport(handler)
        ) as http_client:
            client = B029GatewayClient.from_credential_file(http_client, _credential_file(tmp_path))
            response = await client.embed_texts(("query", "rule"))

        assert response.vectors == ((1.0, 0.0), (0.0, 1.0))
        assert response.model_id == "BAAI/bge-m3"

    asyncio.run(exercise())
