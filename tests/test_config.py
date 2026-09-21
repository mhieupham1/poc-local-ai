from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from local_ai_lab.config import Settings, config_fingerprint, validate_env_template


def write_credential(path: Path, value: str = "test-only-value") -> Path:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return path


def valid_settings(tmp_path: Path) -> dict[str, object]:
    return {
        "llm_base_url": "http://127.0.0.1:8000",
        "embedding_base_url": "http://127.0.0.1:8001",
        "credential_file": write_credential(tmp_path / "credential"),
    }


def test_settings_reject_missing_credential_file(tmp_path: Path) -> None:
    values = valid_settings(tmp_path)
    values["credential_file"] = tmp_path / "missing"

    with pytest.raises(ValidationError, match="credential file does not exist"):
        Settings(**values)


def test_settings_reject_group_readable_credential_file(tmp_path: Path) -> None:
    values = valid_settings(tmp_path)
    credential = Path(values["credential_file"])
    credential.chmod(0o640)

    with pytest.raises(ValidationError, match="permission 0600"):
        Settings(**values)


def test_settings_never_read_or_serialize_credential_content(tmp_path: Path) -> None:
    secret = "do-not-leak-this-value"
    values = valid_settings(tmp_path)
    Path(values["credential_file"]).write_text(secret, encoding="utf-8")

    settings = Settings(**values)
    rendered = repr(settings) + settings.model_dump_json()

    assert secret not in rendered
    assert settings.llm_model == "Qwen/Qwen3-VL-8B-Instruct"
    assert settings.embedding_model == "BAAI/bge-m3"


@pytest.mark.parametrize(
    "url",
    [
        "http://user:url-secret@127.0.0.1:8000",
        "http://127.0.0.1:8000?api_key=url-secret",
        "http://127.0.0.1:8000/#token=url-secret",
    ],
)
def test_settings_reject_credentials_or_parameters_in_endpoint_url(
    tmp_path: Path, url: str
) -> None:
    values = valid_settings(tmp_path)
    values["llm_base_url"] = url

    with pytest.raises(ValidationError, match="must not contain userinfo, query, or fragment"):
        Settings(**values)


def test_config_fingerprint_is_stable_and_contains_no_secret(tmp_path: Path) -> None:
    settings = Settings(**valid_settings(tmp_path))

    first = config_fingerprint(settings)
    second = config_fingerprint(settings)

    assert first == second
    assert len(first) == 8
    assert "test-only-value" not in first


def test_example_env_template_has_all_required_keys() -> None:
    result = validate_env_template(Path(".env.example"))
    env_values = dict(
        line.split("=", maxsplit=1)
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert result.valid is True
    assert result.missing_keys == ()
    assert json.loads(result.model_dump_json())["valid"] is True
    assert env_values["AI_LLM_MODEL"] == "Qwen/Qwen3-VL-8B-Instruct"
