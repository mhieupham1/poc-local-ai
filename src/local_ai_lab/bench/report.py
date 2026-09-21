from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_ai_lab.bench.metrics import summarize
from local_ai_lab.bench.models import RequestResult

__all__ = ["RequestResult", "ReportPaths", "write_report"]


@dataclass(frozen=True)
class ReportPaths:
    raw_jsonl: Path
    summary_json: Path
    summary_markdown: Path


def _distribution(results: list[RequestResult], field: str) -> dict[str, float | int] | None:
    values = [
        float(value)
        for result in results
        if result.success and (value := getattr(result, field)) is not None
    ]
    return asdict(summarize(values)) if values else None


def _evaluation_summary(results: list[RequestResult]) -> dict[str, float | int | None]:
    evaluated = [
        result.evaluation_passed for result in results if result.evaluation_passed is not None
    ]
    passed = sum(value is True for value in evaluated)
    return {
        "evaluated": len(evaluated),
        "passed": passed,
        "pass_rate": passed / len(evaluated) if evaluated else None,
    }


def _evaluation_by_case(results: list[RequestResult]) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[RequestResult]] = {}
    for result in results:
        if result.case_id is not None and result.evaluation_passed is not None:
            groups.setdefault(result.case_id, []).append(result)
    return {case_id: _evaluation_summary(group) for case_id, group in sorted(groups.items())}


def _by_concurrency(
    results: list[RequestResult], level_wall_seconds: dict[int, float]
) -> dict[str, dict[str, Any]]:
    groups: dict[int, list[RequestResult]] = {}
    for result in results:
        groups.setdefault(result.concurrency, []).append(result)
    summaries: dict[str, dict[str, Any]] = {}
    for concurrency, group in sorted(groups.items()):
        failures = sum(not result.success for result in group)
        embedding_rates = [
            result.output_items / result.e2e_seconds
            for result in group
            if result.success and result.output_items is not None and result.e2e_seconds > 0
        ]
        wall_seconds = level_wall_seconds.get(concurrency)
        output_tokens = sum(result.output_tokens or 0 for result in group if result.success)
        output_items = sum(result.output_items or 0 for result in group if result.success)
        summaries[str(concurrency)] = {
            "requests": len(group),
            "failures": failures,
            "error_rate": failures / len(group),
            "wall_seconds": wall_seconds,
            "aggregate_output_tokens_per_second": (
                output_tokens / wall_seconds if wall_seconds else None
            ),
            "aggregate_embedding_items_per_second": (
                output_items / wall_seconds if wall_seconds else None
            ),
            "ttft_seconds": _distribution(group, "ttft_seconds"),
            "e2e_seconds": _distribution(group, "e2e_seconds"),
            "decoding_tokens_per_second": _distribution(group, "decoding_tokens_per_second"),
            "request_output_tokens_per_second": _distribution(
                group, "request_output_tokens_per_second"
            ),
            "embedding_items_per_second": (
                asdict(summarize(embedding_rates)) if embedding_rates else None
            ),
            "evaluation": _evaluation_summary(group),
        }
    return summaries


def _gpu_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(field: str) -> float | None:
        values = [
            float(sample[field])
            for sample in samples
            if field in sample and sample[field] is not None
        ]
        return max(values) if values else None

    return {
        "sample_count": len(samples),
        "peak_memory_used_mib": maximum("memory_used_mib"),
        "peak_utilization_percent": maximum("utilization_percent"),
        "peak_temperature_celsius": maximum("temperature_celsius"),
        "peak_power_watts": maximum("power_watts"),
        "samples": samples,
    }


def write_report(
    *,
    results: list[RequestResult],
    output_dir: Path,
    workload_sha256: str,
    wall_seconds: float,
    level_wall_seconds: dict[int, float] | None = None,
    gpu_samples: list[dict[str, Any]],
) -> ReportPaths:
    if len(workload_sha256) != 64:
        raise ValueError("workload_sha256 must contain 64 hexadecimal characters")
    if wall_seconds <= 0:
        raise ValueError("wall_seconds must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = ReportPaths(
        raw_jsonl=output_dir / "raw.jsonl",
        summary_json=output_dir / "summary.json",
        summary_markdown=output_dir / "summary.md",
    )
    raw = "".join(
        json.dumps(result.model_dump(mode="json"), sort_keys=True) + "\n" for result in results
    )
    output_tokens = sum(result.output_tokens or 0 for result in results if result.success)
    output_items = sum(result.output_items or 0 for result in results if result.success)
    failures = sum(not result.success for result in results)
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workload_sha256": workload_sha256,
        "wall_seconds": wall_seconds,
        "requests": len(results),
        "failures": failures,
        "error_rate": failures / len(results) if results else 0.0,
        "aggregate_output_tokens_per_second": output_tokens / wall_seconds,
        "aggregate_embedding_items_per_second": output_items / wall_seconds,
        "ttft_seconds": _distribution(results, "ttft_seconds"),
        "e2e_seconds": _distribution(results, "e2e_seconds"),
        "decoding_tokens_per_second": _distribution(results, "decoding_tokens_per_second"),
        "evaluation": _evaluation_summary(results),
        "evaluation_by_case": _evaluation_by_case(results),
        "by_concurrency": _by_concurrency(results, level_wall_seconds or {}),
        "gpu": _gpu_summary(gpu_samples),
    }
    markdown = _markdown(summary)
    _atomic_write(paths.raw_jsonl, raw)
    _atomic_write(paths.summary_json, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _atomic_write(paths.summary_markdown, markdown)
    return paths


def _markdown(summary: dict[str, Any]) -> str:
    def p95(metric: str) -> str:
        value = summary.get(metric)
        return "n/a" if not value else f"{value['p95']:.4f}"

    concurrency_rows = "".join(
        f"| {level} | {values['requests']} | {values['failures']} | "
        f"{p95_from(values, 'ttft_seconds')} | {p95_from(values, 'e2e_seconds')} | "
        f"{rate_from(values, 'aggregate_output_tokens_per_second')} |\n"
        for level, values in summary["by_concurrency"].items()
    )
    evaluation = summary["evaluation"]
    evaluation_rate = "n/a" if evaluation["pass_rate"] is None else f"{evaluation['pass_rate']:.2%}"
    evaluation_rows = "".join(
        f"| {case_id} | {values['evaluated']} | {values['passed']} | {values['pass_rate']:.2%} |\n"
        for case_id, values in summary["evaluation_by_case"].items()
        if values["pass_rate"] is not None
    )
    return (
        "# Benchmark Summary\n\n"
        "| Metric | Value |\n"
        "|---|---:|\n"
        f"| Requests | {summary['requests']} |\n"
        f"| Failures | {summary['failures']} |\n"
        f"| Error rate | {summary['error_rate']:.2%} |\n"
        f"| Long-context evaluated | {evaluation['evaluated']} |\n"
        f"| Long-context pass rate | {evaluation_rate} |\n"
        f"| TTFT p95 (s) | {p95('ttft_seconds')} |\n"
        f"| E2E p95 (s) | {p95('e2e_seconds')} |\n"
        "| Aggregate output tokens/s | "
        f"{summary['aggregate_output_tokens_per_second']:.2f} |\n"
        "| Aggregate embedding items/s | "
        f"{summary['aggregate_embedding_items_per_second']:.2f} |\n"
        f"| GPU samples | {summary['gpu']['sample_count']} |\n"
        "\n## By concurrency\n\n"
        "| Concurrency | Requests | Failures | TTFT p95 (s) | E2E p95 (s) | "
        "Aggregate output tokens/s |\n"
        "|---:|---:|---:|---:|---:|---:|\n"
        f"{concurrency_rows}"
        "\n## Long-context evaluation by case\n\n"
        "| Case | Evaluated | Passed | Pass rate |\n"
        "|---|---:|---:|---:|\n"
        f"{evaluation_rows}"
    )


def p95_from(summary: dict[str, Any], metric: str) -> str:
    value = summary.get(metric)
    return "n/a" if not value else f"{value['p95']:.4f}"


def rate_from(summary: dict[str, Any], metric: str) -> str:
    value = summary.get(metric)
    return "n/a" if value is None else f"{value:.2f}"


def _atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
