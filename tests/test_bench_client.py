from __future__ import annotations

import asyncio
import importlib
import json

import httpx
import pytest


def _client_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.bench.client")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark HTTP client is not implemented: {exc}")


def test_chat_benchmark_uses_stream_usage_and_records_first_content_chunk() -> None:
    bench = _client_module()
    observed: dict[str, object] = {}

    def upstream(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        body = (
            'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"xin"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":3}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def run() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="http://gateway"
        ) as client:
            return await bench.benchmark_chat(  # type: ignore[attr-defined]
                client=client,
                path="/v1/chat/completions",
                credential="secret-token",
                request_id="req-001",
                payload={"model": "local-vision-language", "messages": []},
            )

    result = asyncio.run(run())

    assert result.success is True
    assert result.output_tokens == 3
    assert result.prompt_tokens == 4
    assert result.ttft_seconds is not None
    assert result.e2e_seconds > 0
    assert result.request_id == "req-001"
    assert observed["stream"] is True
    assert observed["stream_options"] == {"include_usage": True}


def test_chat_benchmark_fails_closed_when_server_omits_usage() -> None:
    bench = _client_module()

    def upstream(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"xin"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )

    async def run() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="http://gateway"
        ) as client:
            return await bench.benchmark_chat(  # type: ignore[attr-defined]
                client=client,
                path="/v1/chat/completions",
                credential="secret-token",
                request_id="req-002",
                payload={"model": "local-vision-language", "messages": []},
            )

    result = asyncio.run(run())

    assert result.success is False
    assert result.error == "response did not include token usage"


@pytest.mark.parametrize(
    ("chunks", "expected_passed"),
    [
        (("LC-128-", "MIDDLE-7392"), True),
        (("không ", "tìm thấy"), False),
    ],
)
def test_chat_benchmark_scores_expected_marker_without_storing_response(
    chunks: tuple[str, str], expected_passed: bool
) -> None:
    bench = _client_module()

    def upstream(_: httpx.Request) -> httpx.Response:
        body = (
            f'data: {{"choices":[{{"delta":{{"content":"{chunks[0]}"}}}}]}}\n\n'
            f'data: {{"choices":[{{"delta":{{"content":"{chunks[1]}"}}}}]}}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":112,"completion_tokens":4}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def run() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="http://gateway"
        ) as client:
            return await bench.benchmark_chat(  # type: ignore[attr-defined]
                client=client,
                path="/v1/chat/completions",
                credential="secret-token",
                request_id="req-long",
                case_id="long-128-middle",
                expected_contains="LC-128-MIDDLE-7392",
                payload={"model": "local-vision-language", "messages": []},
            )

    result = asyncio.run(run())

    assert result.case_id == "long-128-middle"
    assert result.evaluation_passed is expected_passed
    assert "response" not in result.model_dump()


def test_embedding_benchmark_records_latency_and_vector_count() -> None:
    bench = _client_module()

    def upstream(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2], "index": 0},
                    {"embedding": [0.2, 0.1], "index": 1},
                ],
                "model": "BAAI/bge-m3",
                "usage": {"prompt_tokens": 7, "total_tokens": 7},
            },
        )

    async def run() -> object:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="http://gateway"
        ) as client:
            return await bench.benchmark_embedding(  # type: ignore[attr-defined]
                client=client,
                path="/v1/embeddings",
                credential="secret-token",
                request_id="embed-001",
                payload={"model": "BAAI/bge-m3", "input": ["a", "b"]},
                concurrency=4,
            )

    result = asyncio.run(run())

    assert result.success is True
    assert result.concurrency == 4
    assert result.prompt_tokens == 7
    assert result.output_items == 2
    assert result.e2e_seconds > 0
