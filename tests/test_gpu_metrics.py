from __future__ import annotations

import asyncio
import importlib
import subprocess

import pytest


def _gpu_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.monitoring.gpu")
    except ModuleNotFoundError as exc:
        pytest.fail(f"GPU metric parser is not implemented: {exc}")


def test_parse_nvidia_smi_preserves_each_gpu_and_units() -> None:
    gpu = _gpu_module()
    raw = (
        "GPU-aaa, NVIDIA RTX 4090, 73, 18321, 24564, 67, 392.50\n"
        "GPU-bbb, L40S, 51, 12000, 46068, 58, 210.00\n"
    )

    samples = gpu.parse_nvidia_smi_csv(raw)  # type: ignore[attr-defined]

    assert [sample.uuid for sample in samples] == ["GPU-aaa", "GPU-bbb"]
    assert samples[0].utilization_percent == pytest.approx(73.0)
    assert samples[0].memory_used_mib == pytest.approx(18321.0)
    assert samples[0].temperature_celsius == pytest.approx(67.0)
    assert samples[0].power_watts == pytest.approx(392.5)


def test_parse_nvidia_smi_rejects_missing_or_non_finite_fields() -> None:
    gpu = _gpu_module()

    with pytest.raises(ValueError, match="7 fields"):
        gpu.parse_nvidia_smi_csv("GPU-aaa, RTX 4090, 73")  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="finite"):
        gpu.parse_nvidia_smi_csv(  # type: ignore[attr-defined]
            "GPU-aaa, RTX 4090, nan, 10, 20, 30, 40"
        )


def test_parse_nvidia_smi_keeps_sample_when_optional_sensor_is_unavailable() -> None:
    gpu = _gpu_module()

    samples = gpu.parse_nvidia_smi_csv(  # type: ignore[attr-defined]
        "GPU-aaa, Virtual GPU, 73, 1024, 24564, N/A, [N/A]"
    )

    assert samples[0].utilization_percent == pytest.approx(73.0)
    assert samples[0].temperature_celsius is None
    assert samples[0].power_watts is None


def test_periodic_sampler_collects_until_stop_signal() -> None:
    gpu = _gpu_module()
    calls = 0

    async def run() -> list[dict[str, float]]:
        stop = asyncio.Event()

        def snapshot() -> list[dict[str, float]]:
            nonlocal calls
            calls += 1
            if calls == 3:
                stop.set()
            return [{"memory_used_mib": float(calls)}]

        return await gpu.sample_periodically(  # type: ignore[attr-defined]
            stop=stop, snapshot=snapshot, interval_seconds=0.001
        )

    samples = asyncio.run(run())

    assert [sample["memory_used_mib"] for sample in samples] == [1.0, 2.0, 3.0]


def test_capture_nvidia_smi_returns_empty_when_binary_is_unavailable() -> None:
    gpu = _gpu_module()

    def unavailable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    assert gpu.capture_nvidia_smi(run=unavailable) == []  # type: ignore[attr-defined]
