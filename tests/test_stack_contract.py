from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml


def _stack_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.stack")
    except ModuleNotFoundError as exc:
        pytest.fail(f"stack validation is not implemented: {exc}")


def test_compose_exposes_only_gateway_and_local_operator_ports() -> None:
    stack = _stack_module()

    result = stack.validate_compose(Path("compose.yaml"))  # type: ignore[attr-defined]

    assert result.valid is True
    assert result.errors == ()
    assert result.published_ports == {
        "gateway": ("127.0.0.1:8443:8080",),
        "grafana": ("127.0.0.1:3000:3000",),
        "keycloak": ("127.0.0.1:8081:8080",),
        "prometheus": ("127.0.0.1:9090:9090",),
    }
    assert "llm" not in result.published_ports
    assert "embedding" not in result.published_ports


def test_default_gpu_profile_uses_pinned_qwen3_vl_8b() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    command = compose["services"]["llm"]["command"]
    env_template = Path("config/gpu.env.example").read_text(encoding="utf-8")
    env_values = dict(
        line.split("=", maxsplit=1)
        for line in env_template.splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert "${LLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct}" in command
    assert "${LLM_REVISION:-0c351dd01ed87e9c1b53cbc748cba10e6187ff3b}" in command
    assert env_values["LLM_MODEL"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert env_values["LLM_REVISION"] == "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b"
    assert "32 GB NVIDIA GPU target" in env_template
    assert "TEI image below targets Ada / compute capability 8.9" in env_template


def test_compose_validation_rejects_model_port_published_on_all_interfaces(
    tmp_path: Path,
) -> None:
    stack = _stack_module()
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n  llm:\n    image: example.invalid/llm:1\n    ports:\n      - '8000:8000'\n"
    )

    result = stack.validate_compose(compose)  # type: ignore[attr-defined]

    assert result.valid is False
    assert any("llm" in error and "publish" in error for error in result.errors)


def test_compose_validation_rejects_mutable_latest_image(tmp_path: Path) -> None:
    stack = _stack_module()
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  llm: {image: 'vendor/llm:latest'}\n"
        "  embedding: {image: 'vendor/embed:1.0'}\n"
        "  gateway: {image: 'vendor/gateway:1.0'}\n"
        "  prometheus: {image: 'vendor/prometheus:1.0'}\n"
        "  grafana: {image: 'vendor/grafana:1.0'}\n"
        "  dcgm-exporter: {image: 'vendor/dcgm:1.0'}\n"
    )

    result = stack.validate_compose(compose)  # type: ignore[attr-defined]

    assert result.valid is False
    assert any("mutable latest" in error for error in result.errors)


def test_compose_validation_applies_runtime_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _stack_module()
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  llm: {image: '${VLLM_IMAGE:-vendor/llm:1.0}'}\n"
        "  embedding: {image: 'vendor/embed:1.0'}\n"
        "  gateway: {image: 'vendor/gateway:1.0'}\n"
        "  prometheus: {image: 'vendor/prometheus:1.0'}\n"
        "  grafana: {image: 'vendor/grafana:1.0'}\n"
        "  dcgm-exporter: {image: 'vendor/dcgm:1.0'}\n"
    )
    env_file = tmp_path / "gpu.env"
    env_file.write_text("VLLM_IMAGE=vendor/llm:latest\n")
    monkeypatch.delenv("VLLM_IMAGE", raising=False)

    result = stack.validate_compose(  # type: ignore[attr-defined]
        compose, env_file=env_file
    )

    assert result.valid is False
    assert any("mutable latest" in error for error in result.errors)


def test_shell_environment_takes_precedence_over_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _stack_module()
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  llm: {image: '${VLLM_IMAGE:-vendor/llm:1.0}'}\n"
        "  embedding: {image: 'vendor/embed:1.0'}\n"
        "  gateway: {image: 'vendor/gateway:1.0'}\n"
        "  prometheus: {image: 'vendor/prometheus:1.0'}\n"
        "  grafana: {image: 'vendor/grafana:1.0'}\n"
        "  dcgm-exporter: {image: 'vendor/dcgm:1.0'}\n"
    )
    env_file = tmp_path / "gpu.env"
    env_file.write_text("VLLM_IMAGE=vendor/llm:1.0\n")
    monkeypatch.setenv("VLLM_IMAGE", "vendor/llm:latest")

    result = stack.validate_compose(  # type: ignore[attr-defined]
        compose, env_file=env_file
    )

    assert result.valid is False
    assert any("mutable latest" in error for error in result.errors)
