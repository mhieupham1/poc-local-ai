from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _report_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.bench.report")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark reporting is not implemented: {exc}")


def test_report_writes_raw_summary_and_marks_failed_requests(tmp_path: Path) -> None:
    report = _report_module()
    results = [
        report.RequestResult(  # type: ignore[attr-defined]
            request_id="ok-1",
            concurrency=2,
            success=True,
            status_code=200,
            prompt_tokens=4,
            output_tokens=6,
            ttft_seconds=0.2,
            e2e_seconds=1.2,
            tpot_seconds=0.2,
            decoding_tokens_per_second=5.0,
            request_output_tokens_per_second=5.0,
            error=None,
            output_items=None,
        ),
        report.RequestResult(  # type: ignore[attr-defined]
            request_id="bad-1",
            concurrency=2,
            success=False,
            status_code=503,
            prompt_tokens=None,
            output_tokens=None,
            ttft_seconds=None,
            e2e_seconds=0.1,
            tpot_seconds=None,
            decoding_tokens_per_second=None,
            request_output_tokens_per_second=None,
            error="upstream returned HTTP 503",
            output_items=None,
        ),
    ]

    paths = report.write_report(  # type: ignore[attr-defined]
        results=results,
        output_dir=tmp_path / "result",
        workload_sha256="a" * 64,
        wall_seconds=1.5,
        level_wall_seconds={2: 1.25},
        gpu_samples=[{"uuid": "GPU-a", "memory_used_mib": 1234.0}],
    )

    summary = json.loads(paths.summary_json.read_text())
    raw_lines = paths.raw_jsonl.read_text().splitlines()
    assert summary["requests"] == 2
    assert summary["failures"] == 1
    assert summary["error_rate"] == pytest.approx(0.5)
    assert summary["aggregate_output_tokens_per_second"] == pytest.approx(4.0)
    assert summary["ttft_seconds"]["p50"] == pytest.approx(0.2)
    assert summary["by_concurrency"]["2"]["requests"] == 2
    assert summary["by_concurrency"]["2"]["failures"] == 1
    assert summary["by_concurrency"]["2"]["wall_seconds"] == pytest.approx(1.25)
    assert summary["by_concurrency"]["2"]["aggregate_output_tokens_per_second"] == pytest.approx(
        4.8
    )
    assert summary["by_concurrency"]["2"]["ttft_seconds"]["p95"] == pytest.approx(0.2)
    assert summary["gpu"]["sample_count"] == 1
    assert len(raw_lines) == 2
    assert "Authorization" not in paths.raw_jsonl.read_text()
    assert paths.summary_markdown.is_file()


def test_report_summarizes_long_context_evaluation_without_response_text(tmp_path: Path) -> None:
    report = _report_module()
    results = [
        report.RequestResult(  # type: ignore[attr-defined]
            request_id=f"req-{passed}",
            case_id=f"long-128-{position}",
            concurrency=1,
            success=True,
            status_code=200,
            prompt_tokens=112,
            output_tokens=4,
            output_items=None,
            ttft_seconds=0.2,
            e2e_seconds=0.5,
            tpot_seconds=0.1,
            decoding_tokens_per_second=10.0,
            request_output_tokens_per_second=8.0,
            evaluation_passed=passed,
            error=None,
        )
        for passed, position in ((True, "start"), (False, "middle"))
    ]

    paths = report.write_report(  # type: ignore[attr-defined]
        results=results,
        output_dir=tmp_path / "result",
        workload_sha256="b" * 64,
        wall_seconds=1.0,
        level_wall_seconds={1: 1.0},
        gpu_samples=[],
    )

    summary = json.loads(paths.summary_json.read_text())
    assert summary["evaluation"] == {"evaluated": 2, "passed": 1, "pass_rate": 0.5}
    assert summary["evaluation_by_case"] == {
        "long-128-middle": {"evaluated": 1, "passed": 0, "pass_rate": 0.0},
        "long-128-start": {"evaluated": 1, "passed": 1, "pass_rate": 1.0},
    }
    assert summary["by_concurrency"]["1"]["evaluation"]["pass_rate"] == 0.5
    assert "response" not in paths.raw_jsonl.read_text()
