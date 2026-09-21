from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from local_ai_lab.manifest import ExperimentManifest, ExperimentResult, write_manifest_atomic


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "experiment_id": "phase-01-unit-test",
        "config_fingerprint": "12ab34cd",
        "started_at": datetime(2026, 9, 14, 3, 0, tzinfo=UTC),
        "git_commit": "a" * 40,
        "hardware": {"cpu": "test", "ram_gb": 16},
        "software": {"python": "3.12.7"},
        "models": {"llm": f"Qwen/Qwen3-VL-8B-Instruct@{'c' * 40}"},
        "serving": {"max_model_len": 8192, "streaming": True},
        "workload_sha256": "b" * 64,
    }


def test_manifest_json_round_trip_preserves_contract() -> None:
    manifest = ExperimentManifest(**valid_manifest())

    restored = ExperimentManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert restored.started_at.tzinfo is UTC


def test_manifest_rejects_naive_or_non_utc_timestamp() -> None:
    naive = valid_manifest()
    naive["started_at"] = datetime(2026, 9, 14, 3, 0)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        ExperimentManifest(**naive)

    non_utc = valid_manifest()
    non_utc["started_at"] = datetime(2026, 9, 14, 10, 0, tzinfo=timezone(timedelta(hours=7)))
    with pytest.raises(ValidationError, match="normalized to UTC"):
        ExperimentManifest(**non_utc)


def test_manifest_rejects_invalid_workload_hash() -> None:
    values = valid_manifest()
    values["workload_sha256"] = "not-a-sha256"

    with pytest.raises(ValidationError, match="64 lowercase hexadecimal"):
        ExperimentManifest(**values)


@pytest.mark.parametrize("field", ["hardware", "software", "models", "serving"])
def test_manifest_rejects_empty_reproducibility_field(field: str) -> None:
    values = valid_manifest()
    values[field] = {}

    with pytest.raises(ValidationError, match=f"{field} must not be empty"):
        ExperimentManifest(**values)


@pytest.mark.parametrize("secret_key", ["api_key", "clientSecret", "access-token", "password"])
def test_manifest_rejects_secret_like_keys(secret_key: str) -> None:
    values = valid_manifest()
    values["serving"] = {"max_model_len": 8192, secret_key: "manifest-secret"}

    with pytest.raises(ValidationError, match="secret-like key"):
        ExperimentManifest(**values)


def test_manifest_rejects_unapproved_metadata_key() -> None:
    values = valid_manifest()
    values["serving"] = {"max_model_len": 8192, "notes": "could-hide-a-secret"}

    with pytest.raises(ValidationError, match="unsupported key"):
        ExperimentManifest(**values)


def test_manifest_requires_model_commit_revision() -> None:
    values = valid_manifest()
    values["models"] = {"llm": "Qwen/Qwen3-VL-8B-Instruct@main"}

    with pytest.raises(ValidationError, match="40-character commit revision"):
        ExperimentManifest(**values)


def test_result_schema_records_config_fingerprint_without_raw_config() -> None:
    result = ExperimentResult(
        schema_version="1.0",
        experiment_id="phase-01-unit-test",
        config_fingerprint="12ab34cd",
        status="passed",
        metrics={"ttft_ms": 123.4},
        artifacts={"manifest": "reports/phase-01/manifest.json"},
    )

    rendered = result.model_dump_json()
    assert result.config_fingerprint == "12ab34cd"
    assert "credential" not in rendered


def test_result_rejects_secret_or_unapproved_artifact_metadata() -> None:
    with pytest.raises(ValidationError, match="secret-like key"):
        ExperimentResult(
            schema_version="1.0",
            experiment_id="phase-01-unit-test",
            config_fingerprint="12ab34cd",
            status="failed",
            metrics={},
            artifacts={"credential": "result-secret"},
        )


@pytest.mark.parametrize("absolute_path", [r"C:\tmp\result.json", r"\\server\share\result.json"])
def test_result_rejects_windows_absolute_artifact_path(absolute_path: str) -> None:
    with pytest.raises(ValidationError, match="relative path"):
        ExperimentResult(
            schema_version="1.0",
            experiment_id="phase-01-unit-test",
            config_fingerprint="12ab34cd",
            status="passed",
            metrics={},
            artifacts={"manifest": absolute_path},
        )

    with pytest.raises(ValidationError, match="relative path"):
        ExperimentResult(
            schema_version="1.0",
            experiment_id="phase-01-unit-test",
            config_fingerprint="12ab34cd",
            status="passed",
            metrics={},
            artifacts={"manifest": "/tmp/result-secret"},
        )


def test_atomic_writer_creates_valid_json_without_temp_files(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "manifest.json"
    manifest = ExperimentManifest(**valid_manifest())

    write_manifest_atomic(destination, manifest)

    restored = ExperimentManifest.model_validate_json(destination.read_text(encoding="utf-8"))
    assert restored == manifest
    assert list(destination.parent.glob("*.tmp")) == []
