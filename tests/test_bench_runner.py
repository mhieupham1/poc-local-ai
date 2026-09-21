from __future__ import annotations

import asyncio
import importlib

import pytest


def _runner_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.bench.runner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"benchmark runner is not implemented: {exc}")


def test_runner_never_exceeds_concurrency_and_preserves_result_order() -> None:
    runner = _runner_module()
    active = 0
    observed_peak = 0

    async def request(item: int) -> int:
        nonlocal active, observed_peak
        active += 1
        observed_peak = max(observed_peak, active)
        await asyncio.sleep(0.005)
        active -= 1
        return item * 10

    result = asyncio.run(
        runner.run_concurrent(  # type: ignore[attr-defined]
            items=[1, 2, 3, 4, 5], concurrency=2, operation=request
        )
    )

    assert result == [10, 20, 30, 40, 50]
    assert observed_peak == 2


def test_runner_rejects_non_positive_concurrency() -> None:
    runner = _runner_module()

    async def request(item: int) -> int:
        return item

    with pytest.raises(ValueError, match="positive"):
        asyncio.run(
            runner.run_concurrent(  # type: ignore[attr-defined]
                items=[1], concurrency=0, operation=request
            )
        )
