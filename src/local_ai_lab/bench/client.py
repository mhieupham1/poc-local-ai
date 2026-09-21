from __future__ import annotations

import json
import time
from typing import Any

import httpx

from local_ai_lab.bench.metrics import StreamTiming, calculate_stream_metrics
from local_ai_lab.bench.models import RequestResult


async def benchmark_chat(
    *,
    client: httpx.AsyncClient,
    path: str,
    credential: str,
    request_id: str,
    payload: dict[str, Any],
    concurrency: int = 1,
    case_id: str | None = None,
    expected_contains: str | None = None,
) -> RequestResult:
    request_payload = dict(payload)
    request_payload["stream"] = True
    request_payload["stream_options"] = {"include_usage": True}
    started = time.monotonic()
    first_content_at: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    response_parts: list[str] | None = [] if expected_contains is not None else None

    try:
        async with client.stream(
            "POST",
            path,
            headers={
                "authorization": f"Bearer {credential}",
                "x-request-id": request_id,
            },
            json=request_payload,
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                completed = time.monotonic()
                return _failed(
                    request_id=request_id,
                    case_id=case_id,
                    concurrency=concurrency,
                    status_code=response.status_code,
                    elapsed=completed - started,
                    error=f"upstream returned HTTP {response.status_code}",
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event: dict[str, Any] = json.loads(data)
                except json.JSONDecodeError:
                    completed = time.monotonic()
                    return _failed(
                        request_id=request_id,
                        case_id=case_id,
                        concurrency=concurrency,
                        status_code=response.status_code,
                        elapsed=completed - started,
                        error="malformed SSE JSON",
                    )
                usage = event.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens = _integer_or_none(usage.get("prompt_tokens"))
                    output_tokens = _integer_or_none(usage.get("completion_tokens"))
                if first_content_at is None and _has_content(event):
                    first_content_at = time.monotonic()
                if response_parts is not None:
                    response_parts.extend(_content_parts(event))
        completed = time.monotonic()
    except httpx.TimeoutException:
        completed = time.monotonic()
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=None,
            elapsed=completed - started,
            error="request timed out",
        )
    except httpx.HTTPError:
        completed = time.monotonic()
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=None,
            elapsed=completed - started,
            error="gateway unavailable",
        )

    if first_content_at is None:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=200,
            elapsed=completed - started,
            error="response did not include content",
        )
    if output_tokens is None or prompt_tokens is None or output_tokens < 1:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=200,
            elapsed=completed - started,
            error="response did not include token usage",
        )
    timing = calculate_stream_metrics(
        StreamTiming(
            request_started=started,
            first_token_at=first_content_at,
            completed_at=completed,
            output_tokens=output_tokens,
        )
    )
    return RequestResult(
        request_id=request_id,
        concurrency=concurrency,
        success=True,
        status_code=200,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        output_items=None,
        ttft_seconds=timing.ttft_seconds,
        e2e_seconds=timing.e2e_seconds,
        tpot_seconds=timing.tpot_seconds,
        decoding_tokens_per_second=timing.decoding_tokens_per_second,
        request_output_tokens_per_second=timing.request_output_tokens_per_second,
        error=None,
        case_id=case_id,
        evaluation_passed=(
            expected_contains in "".join(response_parts)
            if expected_contains is not None and response_parts is not None
            else None
        ),
    )


async def benchmark_embedding(
    *,
    client: httpx.AsyncClient,
    path: str,
    credential: str,
    request_id: str,
    payload: dict[str, Any],
    concurrency: int = 1,
    case_id: str | None = None,
) -> RequestResult:
    started = time.monotonic()
    try:
        response = await client.post(
            path,
            headers={
                "authorization": f"Bearer {credential}",
                "x-request-id": request_id,
            },
            json=payload,
        )
    except httpx.TimeoutException:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=None,
            elapsed=time.monotonic() - started,
            error="request timed out",
        )
    except httpx.HTTPError:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=None,
            elapsed=time.monotonic() - started,
            error="gateway unavailable",
        )
    elapsed = time.monotonic() - started
    if response.status_code < 200 or response.status_code >= 300:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=response.status_code,
            elapsed=elapsed,
            error=f"upstream returned HTTP {response.status_code}",
        )
    try:
        document: dict[str, Any] = response.json()
    except (json.JSONDecodeError, TypeError):
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=response.status_code,
            elapsed=elapsed,
            error="embedding response is not valid JSON",
        )
    data = document.get("data")
    usage = document.get("usage")
    if not isinstance(data, list) or not data:
        return _failed(
            request_id=request_id,
            case_id=case_id,
            concurrency=concurrency,
            status_code=response.status_code,
            elapsed=elapsed,
            error="embedding response contains no vectors",
        )
    prompt_tokens = (
        _integer_or_none(usage.get("prompt_tokens")) if isinstance(usage, dict) else None
    )
    return RequestResult(
        request_id=request_id,
        concurrency=concurrency,
        success=True,
        status_code=response.status_code,
        prompt_tokens=prompt_tokens,
        output_tokens=None,
        output_items=len(data),
        ttft_seconds=None,
        e2e_seconds=max(elapsed, 0.0),
        tpot_seconds=None,
        decoding_tokens_per_second=None,
        request_output_tokens_per_second=None,
        error=None,
        case_id=case_id,
    )


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _has_content(event: dict[str, Any]) -> bool:
    return bool(_content_parts(event))


def _content_parts(event: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    choices = event.get("choices")
    if not isinstance(choices, list):
        return parts
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict) and isinstance(delta.get("content"), str) and delta["content"]:
            parts.append(delta["content"])
    return parts


def _failed(
    *,
    request_id: str,
    concurrency: int,
    status_code: int | None,
    elapsed: float,
    error: str,
    case_id: str | None = None,
) -> RequestResult:
    return RequestResult(
        request_id=request_id,
        concurrency=concurrency,
        success=False,
        status_code=status_code,
        prompt_tokens=None,
        output_tokens=None,
        output_items=None,
        ttft_seconds=None,
        e2e_seconds=max(elapsed, 0.0),
        tpot_seconds=None,
        decoding_tokens_per_second=None,
        request_output_tokens_per_second=None,
        error=error,
        case_id=case_id,
    )
