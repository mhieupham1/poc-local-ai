from __future__ import annotations

import importlib

import pytest


def _metrics_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.bench.metrics")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark metrics are not implemented: {exc}")


def test_stream_metrics_exclude_first_token_from_decoding_rate() -> None:
    metrics = _metrics_module()
    sample = metrics.StreamTiming(  # type: ignore[attr-defined]
        request_started=10.0,
        first_token_at=10.25,
        completed_at=11.25,
        output_tokens=6,
    )

    result = metrics.calculate_stream_metrics(sample)  # type: ignore[attr-defined]

    assert result.ttft_seconds == pytest.approx(0.25)
    assert result.e2e_seconds == pytest.approx(1.25)
    assert result.tpot_seconds == pytest.approx(0.2)
    assert result.decoding_tokens_per_second == pytest.approx(5.0)
    assert result.request_output_tokens_per_second == pytest.approx(4.8)


def test_one_token_response_has_no_decoding_metric() -> None:
    metrics = _metrics_module()
    sample = metrics.StreamTiming(  # type: ignore[attr-defined]
        request_started=1.0,
        first_token_at=1.2,
        completed_at=1.2,
        output_tokens=1,
    )

    result = metrics.calculate_stream_metrics(sample)  # type: ignore[attr-defined]

    assert result.tpot_seconds is None
    assert result.decoding_tokens_per_second is None


def test_percentiles_use_linear_interpolation() -> None:
    metrics = _metrics_module()

    result = metrics.summarize([1.0, 2.0, 3.0, 4.0])  # type: ignore[attr-defined]

    assert result.count == 4
    assert result.p50 == pytest.approx(2.5)
    assert result.p95 == pytest.approx(3.85)
