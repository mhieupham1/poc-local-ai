from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamTiming:
    request_started: float
    first_token_at: float
    completed_at: float
    output_tokens: int


@dataclass(frozen=True)
class StreamMetrics:
    ttft_seconds: float
    e2e_seconds: float
    tpot_seconds: float | None
    decoding_tokens_per_second: float | None
    request_output_tokens_per_second: float


@dataclass(frozen=True)
class DistributionSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    p50: float
    p90: float
    p95: float
    p99: float


def calculate_stream_metrics(sample: StreamTiming) -> StreamMetrics:
    if sample.output_tokens < 1:
        raise ValueError("output_tokens must be positive")
    if not sample.request_started <= sample.first_token_at <= sample.completed_at:
        raise ValueError("timestamps must be monotonic")
    ttft = sample.first_token_at - sample.request_started
    e2e = sample.completed_at - sample.request_started
    if e2e <= 0:
        raise ValueError("end-to-end duration must be positive")

    tpot: float | None = None
    decoding_tps: float | None = None
    if sample.output_tokens > 1:
        decoding_duration = sample.completed_at - sample.first_token_at
        if decoding_duration <= 0:
            raise ValueError("multi-token response must have positive decoding duration")
        decoding_tokens = sample.output_tokens - 1
        tpot = decoding_duration / decoding_tokens
        decoding_tps = decoding_tokens / decoding_duration

    return StreamMetrics(
        ttft_seconds=ttft,
        e2e_seconds=e2e,
        tpot_seconds=tpot,
        decoding_tokens_per_second=decoding_tps,
        request_output_tokens_per_second=sample.output_tokens / e2e,
    )


def _percentile(sorted_values: list[float], percentile: float) -> float:
    position = (len(sorted_values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def summarize(values: list[float]) -> DistributionSummary:
    if not values:
        raise ValueError("at least one value is required")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("all values must be finite")
    ordered = sorted(values)
    return DistributionSummary(
        count=len(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        mean=statistics.fmean(ordered),
        p50=_percentile(ordered, 0.50),
        p90=_percentile(ordered, 0.90),
        p95=_percentile(ordered, 0.95),
        p99=_percentile(ordered, 0.99),
    )
