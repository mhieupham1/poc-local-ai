from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "deploy/vast/ROOT/opt/supervisor-scripts"


def _dry_run(name: str, **values: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ["PATH"],
        "LOCAL_AI_SKIP_VAST_UTILS": "1",
        **values,
    }
    return subprocess.run(
        ["bash", str(SCRIPTS / name), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_llm_dry_run_is_loopback_only_and_revision_pinned() -> None:
    result = _dry_run("local-ai-llm.sh", LOCAL_AI_SKIP_DEPENDENCY_WAIT="1")

    assert result.returncode == 0, result.stderr
    assert "Qwen/Qwen3-VL-8B-Instruct" in result.stdout
    assert "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b" in result.stdout
    assert "--host 127.0.0.1" in result.stdout
    assert "--port 8000" in result.stdout
    assert "--gpu-memory-utilization 0.72" in result.stdout


def test_embedding_dry_run_uses_bge_m3_pooling_on_loopback() -> None:
    result = _dry_run("local-ai-embedding.sh")

    assert result.returncode == 0, result.stderr
    assert "BAAI/bge-m3" in result.stdout
    assert "5617a9f61b028005a4858fdac845db406aefb181" in result.stdout
    assert "--runner pooling" in result.stdout
    assert "BgeM3EmbeddingModel" in result.stdout
    assert "--pooler-config.task embed" in result.stdout
    assert "--host 127.0.0.1" in result.stdout
    assert "--port 8001" in result.stdout


def test_model_scripts_reject_unsafe_combined_gpu_fraction() -> None:
    result = _dry_run(
        "local-ai-embedding.sh",
        LLM_GPU_MEMORY_UTILIZATION="0.80",
        EMBEDDING_GPU_MEMORY_UTILIZATION="0.20",
    )

    assert result.returncode == 2
    assert "combined GPU memory utilization must be <= 0.90" in result.stderr


def test_gateway_refuses_to_start_without_a_token() -> None:
    result = _dry_run(
        "local-ai-gateway.sh",
        LOCAL_AI_SKIP_DEPENDENCY_WAIT="1",
    )

    assert result.returncode == 2
    assert "OPEN_BUTTON_TOKEN or LOCAL_AI_API_TOKEN is required" in result.stderr


def test_gateway_dry_run_never_prints_token() -> None:
    secret = "a-secret-value-that-is-longer-than-thirty-two"
    result = _dry_run(
        "local-ai-gateway.sh",
        LOCAL_AI_SKIP_DEPENDENCY_WAIT="1",
        OPEN_BUTTON_TOKEN=secret,
    )

    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout + result.stderr
    assert "--host 127.0.0.1 --port 18000" in result.stdout


def test_token_writer_creates_private_file_without_printing_secret(tmp_path: Path) -> None:
    secret = "another-secret-value-that-is-longer-than-thirty-two"
    token_file = tmp_path / "runtime" / "gateway-token"
    common = SCRIPTS / "local-ai-common.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; write_token_file "$2" "$LOCAL_AI_API_TOKEN"',
            "test-token-writer",
            str(common),
            str(token_file),
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "LOCAL_AI_API_TOKEN": secret},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert token_file.read_text() == secret
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert secret not in result.stdout + result.stderr


def test_template_is_private_and_exposes_portal_plus_gateway() -> None:
    template = json.loads((ROOT / "deploy/vast/template.json.example").read_text())

    assert template["private"] is True
    assert template["runtype"] == "ssh"
    assert template["tag"] == "2026-09-15.1"
    assert template["use_ssh"] is True
    assert template["ssh_direct"] is True
    assert template["recommended_disk_space"] == 100
    assert "-p 1111:1111" in template["env"]
    assert "-p 8080:8080" in template["env"]
    assert "8000:8000" not in template["env"]
    assert "8001:8001" not in template["env"]
    assert "localhost:1111:11111:/:Instance Portal" in template["env"]
    assert "localhost:8080:18000:/:Local AI API" in template["env"]


def test_template_contains_no_credentials() -> None:
    template_path = ROOT / "deploy/vast/template.json.example"
    raw = template_path.read_text()
    template = json.loads(raw)

    assert "HF_TOKEN=" not in raw
    assert "OPEN_BUTTON_TOKEN=" not in raw
    assert "LOCAL_AI_API_TOKEN=" not in raw
    assert template["docker_login_pass"] == ""
    assert template["docker_login_user"] == ""


def test_image_disables_inherited_vllm_ray_and_model_ui_programs() -> None:
    dockerfile = (ROOT / "deploy/vast/Dockerfile").read_text()

    for inherited_config in ("vllm.conf", "ray.conf", "model-ui.conf"):
        assert f"/etc/supervisor/conf.d/{inherited_config}" in dockerfile
    assert "/etc/vast_capabilities.d/30-vllm.yaml" in dockerfile

    capabilities = (ROOT / "deploy/vast/ROOT/etc/vast_capabilities.d/30-local-ai.yaml").read_text()
    assert 'service: "Local AI API"' in capabilities
    assert "capabilities: [chat, embeddings, models]" in capabilities


def test_vast_client_env_uses_one_base_url_for_both_capabilities() -> None:
    values = dotenv_values(ROOT / "config/vast-client.env.example")

    assert values["AI_LLM_BASE_URL"] == "https://your-ai-host.trycloudflare.com"
    assert values["AI_EMBEDDING_BASE_URL"] == values["AI_LLM_BASE_URL"]
    assert values["AI_CREDENTIAL_FILE"] == "secrets/vast-api-token"


def test_common_loads_vast_utilities_safely_under_nounset(tmp_path: Path) -> None:
    utils = tmp_path / "utils"
    utils.mkdir()
    (utils / "logging.sh").write_text("logpath=$1\n")
    (utils / "cleanup_generic.sh").write_text(":\n")
    (utils / "environment.sh").write_text(":\n")
    common = SCRIPTS / "local-ai-common.sh"

    result = subprocess.run(
        [
            "bash",
            "-c",
            'set -u; source "$1"; load_vast_runtime; printf loaded',
            "test-vast-utils",
            str(common),
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], "VAST_UTILS_DIR": str(utils)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "loaded"


def test_caddy_output_filter_redacts_generated_credentials() -> None:
    secret = "secret-that-must-not-reach-the-portal-log"
    source = "\n".join(
        (
            f"* Your web credentials are: user / {secret}",
            f"* Open button token is also valid: {secret}",
            f"* To make API requests, pass Authorization: Bearer {secret}",
            "Starting Caddy...",
        )
    )
    result = subprocess.run(
        ["bash", str(SCRIPTS / "local-ai-redact-caddy-output.sh")],
        cwd=ROOT,
        input=source,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert secret not in result.stdout + result.stderr
    assert result.stdout.count("[redacted]") == 3
    assert "Starting Caddy..." in result.stdout


def test_caddyfile_protector_sets_mode_0600(tmp_path: Path) -> None:
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text("token matcher")
    caddyfile.chmod(0o644)

    result = subprocess.run(
        ["bash", str(SCRIPTS / "local-ai-protect-caddyfile.sh"), str(caddyfile)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(caddyfile.stat().st_mode) == 0o600


def test_caddy_wrapper_applies_both_credential_hardening_steps() -> None:
    wrapper = (SCRIPTS / "caddy.sh").read_text()
    dockerfile = (ROOT / "deploy/vast/Dockerfile").read_text()

    assert wrapper.index("umask 077") < wrapper.index("caddy_config_manager.py")
    assert wrapper.index("local-ai-protect-caddyfile.sh /etc/Caddyfile") < wrapper.index(
        "caddy_config_manager.py"
    )
    assert "caddy_config_manager.py 2>&1" in wrapper
    assert "| /opt/supervisor-scripts/local-ai-redact-caddy-output.sh" in wrapper
    assert "/opt/supervisor-scripts/caddy.sh" in dockerfile


def test_caddy_manager_build_patch_hashes_password_via_stdin(tmp_path: Path) -> None:
    manager = tmp_path / "caddy_config_manager.py"
    manager.write_text(
        "hashed_password = subprocess.check_output("
        "[CADDY_BIN, 'hash-password', '-p', password]).decode().strip()\n"
    )
    patcher = ROOT / "deploy/vast/patch-caddy-manager.py"

    result = subprocess.run(
        [os.environ.get("PYTHON", "python3"), str(patcher), str(manager)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    patched = manager.read_text()
    assert "'hash-password', '-p', password" not in patched
    assert "[CADDY_BIN, 'hash-password'], input=password.encode()" in patched
    assert "patch-caddy-manager.py" in (ROOT / "deploy/vast/Dockerfile").read_text()


def _run_smoke(
    base_url: str,
    token_file: Path,
    **env_values: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(ROOT / "deploy/vast/smoke.sh"),
            "--base-url",
            base_url,
            "--token-file",
            str(token_file),
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"], **env_values},
        text=True,
        capture_output=True,
        check=False,
    )


def test_smoke_rejects_non_https_base_url(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("x" * 48)
    token.chmod(0o600)

    result = _run_smoke("http://example.test", token)

    assert result.returncode == 2
    assert "base URL must use https" in result.stderr


def test_smoke_requires_private_token_file(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("x" * 48)
    token.chmod(0o644)

    result = _run_smoke("https://example.test", token)

    assert result.returncode == 2
    assert "token file must have mode 0600" in result.stderr


def test_smoke_keeps_token_out_of_curl_process_arguments(tmp_path: Path) -> None:
    secret = "safe-secret-value-that-is-longer-than-thirty-two"
    token = tmp_path / "token"
    token.write_text(secret)
    token.chmod(0o600)
    args_log = tmp_path / "curl-args.log"
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' \"$*\" >>\"${FAKE_CURL_ARGS_LOG}\"
output=''
url=''
while (( $# )); do
  case \"$1\" in
    --output) output=\"$2\"; shift 2 ;;
    --write-out) shift 2 ;;
    https://*) url=\"$1\"; shift ;;
    *) shift ;;
  esac
done
case \"${url}\" in
  */readyz) printf '%s' '{\"status\":\"ready\"}' >\"${output}\" ;;
  */v1/models)
    printf '%s' '{\"detail\":\"unauthorized\"}' >\"${output}\"
    printf '%s' '401'
    ;;
  */v1/chat/completions)
    printf '%s' '{\"choices\":[{\"message\":{\"content\":\"ok\"}}]}' >\"${output}\"
    ;;
  */v1/embeddings) printf '%s' '{\"data\":[{\"embedding\":[0.1],\"index\":0}]}' >\"${output}\" ;;
  *) exit 22 ;;
esac
"""
    )
    fake_curl.chmod(0o755)

    result = _run_smoke(
        "https://example.test",
        token,
        CURL_BIN=str(fake_curl),
        FAKE_CURL_ARGS_LOG=str(args_log),
    )

    assert result.returncode == 0, result.stderr
    logged_args = args_log.read_text()
    assert secret not in logged_args
    assert logged_args.count("/v1/models") == 2
    assert logged_args.count("/v1/chat/completions") == 2
    assert "auth: ok" in result.stdout
    assert "chat: ok" in result.stdout
    assert "vision: ok" in result.stdout
    assert "embedding: ok" in result.stdout
