from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from local_ai_lab.bench.client import benchmark_chat, benchmark_embedding
from local_ai_lab.bench.models import RequestResult
from local_ai_lab.bench.report import ReportPaths, write_report
from local_ai_lab.bench.runner import run_concurrent
from local_ai_lab.gateway.auth import read_token_file
from local_ai_lab.monitoring.gpu import capture_nvidia_smi, sample_periodically


@dataclass(frozen=True)
class WorkloadCase:
    case_id: str
    payload: dict[str, Any]
    expected_contains: str | None = None


def load_workload(path: Path) -> tuple[list[WorkloadCase], str]:
    raw = path.read_bytes()
    cases: list[WorkloadCase] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
            raise ValueError(f"workload line {line_number} must contain a payload object")
        case_id = item.get("id")
        expected_contains = item.get("expected_contains")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"workload line {line_number} must contain a non-empty id")
        if expected_contains is not None and not isinstance(expected_contains, str):
            raise ValueError(f"workload line {line_number} expected_contains must be a string")
        cases.append(
            WorkloadCase(
                case_id=case_id,
                payload=item["payload"],
                expected_contains=expected_contains,
            )
        )
    if not cases:
        raise ValueError("workload must contain at least one case")
    return cases, hashlib.sha256(raw).hexdigest()


async def _run_command(
    *,
    kind: Literal["chat", "embedding"],
    workload: Path,
    output: Path,
    credential_file: Path,
    base_url: str,
    concurrency_levels: tuple[int, ...],
    requests_per_level: int,
    timeout_seconds: float,
) -> ReportPaths:
    cases, workload_sha256 = load_workload(workload)
    credential = read_token_file(credential_file)
    results: list[RequestResult] = []
    level_wall_seconds: dict[int, float] = {}
    started = time.monotonic()
    gpu_stop = asyncio.Event()
    gpu_task = asyncio.create_task(
        sample_periodically(
            stop=gpu_stop,
            snapshot=_capture_gpu_samples,
            interval_seconds=1.0,
        )
    )
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        ) as client:
            for concurrency in concurrency_levels:
                level_started = time.monotonic()
                items = list(range(requests_per_level))

                async def operation(index: int, level: int = concurrency) -> RequestResult:
                    case = cases[index % len(cases)]
                    if kind == "chat":
                        return await benchmark_chat(
                            client=client,
                            path="/v1/chat/completions",
                            credential=credential,
                            request_id=str(uuid.uuid4()),
                            payload=case.payload,
                            concurrency=level,
                            case_id=case.case_id,
                            expected_contains=case.expected_contains,
                        )
                    return await benchmark_embedding(
                        client=client,
                        path="/v1/embeddings",
                        credential=credential,
                        request_id=str(uuid.uuid4()),
                        payload=case.payload,
                        concurrency=level,
                        case_id=case.case_id,
                    )

                results.extend(
                    await run_concurrent(
                        items=items,
                        concurrency=concurrency,
                        operation=operation,
                    )
                )
                level_wall_seconds[concurrency] = time.monotonic() - level_started
    finally:
        gpu_stop.set()
        gpu_samples = await gpu_task
    return write_report(
        results=results,
        output_dir=output,
        workload_sha256=workload_sha256,
        wall_seconds=time.monotonic() - started,
        level_wall_seconds=level_wall_seconds,
        gpu_samples=gpu_samples,
    )


def _capture_gpu_samples() -> list[dict[str, Any]]:
    return [
        {
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "captured_at_monotonic": time.monotonic(),
            "uuid": sample.uuid,
            "name": sample.name,
            "utilization_percent": sample.utilization_percent,
            "memory_used_mib": sample.memory_used_mib,
            "memory_total_mib": sample.memory_total_mib,
            "temperature_celsius": sample.temperature_celsius,
            "power_watts": sample.power_watts,
        }
        for sample in capture_nvidia_smi()
    ]


async def run_chat_command(**kwargs: Any) -> ReportPaths:
    return await _run_command(kind="chat", **kwargs)


async def run_embedding_command(**kwargs: Any) -> ReportPaths:
    return await _run_command(kind="embedding", **kwargs)


def parse_concurrency(value: str) -> tuple[int, ...]:
    try:
        levels = tuple(int(part) for part in value.split(","))
    except ValueError as exc:
        raise ValueError("concurrency must be comma-separated integers") from exc
    if not levels or any(level <= 0 for level in levels):
        raise ValueError("concurrency levels must be positive")
    return levels


def run_chat_command_sync(**kwargs: Any) -> ReportPaths:
    return asyncio.run(run_chat_command(**kwargs))


def run_embedding_command_sync(**kwargs: Any) -> ReportPaths:
    return asyncio.run(run_embedding_command(**kwargs))
