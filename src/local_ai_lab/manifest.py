from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

SECRET_KEY_NAMES = {
    "accesstoken",
    "apikey",
    "clientsecret",
    "credential",
    "password",
    "privatekey",
    "refreshtoken",
}

ALLOWED_MANIFEST_KEYS: dict[str, set[str]] = {
    "hardware": {
        "cpu",
        "cuda_version",
        "disk_gb",
        "driver_version",
        "gpu_count",
        "gpu_model",
        "gpu_uuid",
        "gpu_vram_gb",
        "ram_gb",
        "target",
    },
    "software": {
        "git",
        "kernel",
        "nginx",
        "platform",
        "python",
        "pytorch",
        "qdrant",
        "sentence_transformers",
        "tei",
        "transformers",
        "vllm",
    },
    "models": {"embedding", "llm", "processor", "reranker", "tokenizer", "vision"},
    "serving": {
        "batch_size",
        "dtype",
        "embedding_device",
        "gpu_memory_utilization",
        "host",
        "max_model_len",
        "max_num_seqs",
        "port",
        "profile",
        "quantization",
        "streaming",
        "target",
    },
}

ALLOWED_RESULT_ARTIFACT_KEYS = {
    "environment",
    "manifest",
    "metrics",
    "raw_results",
    "report",
    "summary",
}


def validate_metadata_mapping(field_name: str, mapping: Mapping[str, object]) -> None:
    if not mapping:
        raise ValueError(f"{field_name} must not be empty")
    for key in mapping:
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized in SECRET_KEY_NAMES:
            raise ValueError(f"{field_name} contains secret-like key: {key}")
        if key not in ALLOWED_MANIFEST_KEYS[field_name]:
            raise ValueError(f"{field_name} contains unsupported key: {key}")


class ExperimentManifest(BaseModel):
    schema_version: Literal["1.0"]
    experiment_id: str = Field(min_length=1)
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{8}$")
    started_at: datetime
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    hardware: dict[str, str | int | float]
    software: dict[str, str]
    models: dict[str, str]
    serving: dict[str, str | int | float | bool]
    workload_sha256: str

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware UTC")
        if value.utcoffset() != timedelta(0):
            raise ValueError("started_at must already be normalized to UTC")
        return value.astimezone(UTC)

    @field_validator("workload_sha256")
    @classmethod
    def validate_workload_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("workload_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def validate_reproducibility_and_secrets(self) -> Self:
        validate_metadata_mapping("hardware", self.hardware)
        validate_metadata_mapping("software", self.software)
        validate_metadata_mapping("models", self.models)
        validate_metadata_mapping("serving", self.serving)

        for model_reference in self.models.values():
            if re.fullmatch(r".+@[0-9a-f]{40}", model_reference) is None:
                raise ValueError(
                    "every model must include an immutable 40-character commit revision"
                )
        return self


class ExperimentResult(BaseModel):
    schema_version: Literal["1.0"]
    experiment_id: str = Field(min_length=1)
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{8}$")
    status: Literal["passed", "failed", "interrupted"]
    metrics: dict[str, float]
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_artifact_metadata(self) -> Self:
        for key, value in self.artifacts.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in SECRET_KEY_NAMES:
                raise ValueError(f"artifacts contains secret-like key: {key}")
            if key not in ALLOWED_RESULT_ARTIFACT_KEYS:
                raise ValueError(f"artifacts contains unsupported key: {key}")
            posix_path = PurePosixPath(value)
            windows_path = PureWindowsPath(value)
            if (
                posix_path.is_absolute()
                or windows_path.is_absolute()
                or ".." in posix_path.parts
                or ".." in windows_path.parts
                or "://" in value
            ):
                raise ValueError(f"artifact must be a relative path: {value}")
        return self


def write_manifest_atomic(path: Path, manifest: ExperimentManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(manifest.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
