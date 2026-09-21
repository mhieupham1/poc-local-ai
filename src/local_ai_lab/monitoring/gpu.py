from __future__ import annotations

import asyncio
import math
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuSample:
    uuid: str
    name: str
    utilization_percent: float | None
    memory_used_mib: float | None
    memory_total_mib: float | None
    temperature_celsius: float | None
    power_watts: float | None


def _optional_number(value: str) -> float | None:
    if value.upper() in {"N/A", "[N/A]", "NOT SUPPORTED"}:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("numeric fields must be finite")
    return number


def parse_nvidia_smi_csv(raw: str) -> list[GpuSample]:
    samples: list[GpuSample] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 7:
            raise ValueError(f"line {line_number} must contain 7 fields")
        try:
            numeric = [_optional_number(value) for value in fields[2:]]
        except ValueError as exc:
            raise ValueError(f"line {line_number} numeric fields must be finite") from exc
        samples.append(
            GpuSample(
                uuid=fields[0],
                name=fields[1],
                utilization_percent=numeric[0],
                memory_used_mib=numeric[1],
                memory_total_mib=numeric[2],
                temperature_celsius=numeric[3],
                power_watts=numeric[4],
            )
        )
    return samples


def capture_nvidia_smi(
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[GpuSample]:
    command = [
        "nvidia-smi",
        "--query-gpu=uuid,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = run(command, check=True, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    return parse_nvidia_smi_csv(completed.stdout)


async def sample_periodically[SampleT](
    *,
    stop: asyncio.Event,
    snapshot: Callable[[], list[SampleT]],
    interval_seconds: float,
) -> list[SampleT]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    samples: list[SampleT] = []
    while True:
        samples.extend(await asyncio.to_thread(snapshot))
        if stop.is_set():
            return samples
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
