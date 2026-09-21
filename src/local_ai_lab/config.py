from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from dotenv import dotenv_values
from pydantic import AnyHttpUrl, BaseModel, PositiveInt, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", extra="forbid")

    llm_base_url: AnyHttpUrl
    embedding_base_url: AnyHttpUrl
    credential_file: Path
    llm_model: str = "Qwen/Qwen3-VL-8B-Instruct"
    embedding_model: str = "BAAI/bge-m3"
    request_timeout_seconds: PositiveInt = 120

    @field_validator("llm_base_url", "embedding_base_url")
    @classmethod
    def reject_endpoint_secrets(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("endpoint URL must not contain userinfo, query, or fragment")
        return value

    @field_validator("credential_file")
    @classmethod
    def validate_credential_file(cls, value: Path) -> Path:
        if not value.is_file():
            raise ValueError("credential file does not exist or is not a regular file")
        mode = stat.S_IMODE(value.stat().st_mode)
        if mode != 0o600:
            raise ValueError(f"credential file must have permission 0600, got {mode:04o}")
        return value


class EnvTemplateValidation(BaseModel):
    path: Path
    valid: bool
    missing_keys: tuple[str, ...]
    errors: tuple[str, ...] = ()


def config_fingerprint(settings: Settings) -> str:
    public_config = {
        "llm_base_url": str(settings.llm_base_url),
        "embedding_base_url": str(settings.embedding_base_url),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "request_timeout_seconds": settings.request_timeout_seconds,
    }
    canonical = json.dumps(public_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def validate_env_template(path: Path) -> EnvTemplateValidation:
    required = {
        "AI_LLM_BASE_URL",
        "AI_EMBEDDING_BASE_URL",
        "AI_CREDENTIAL_FILE",
        "AI_LLM_MODEL",
        "AI_EMBEDDING_MODEL",
        "AI_REQUEST_TIMEOUT_SECONDS",
    }
    values = dotenv_values(path)
    missing = tuple(sorted(key for key in required if not values.get(key)))
    errors: list[str] = []

    url_adapter = TypeAdapter(AnyHttpUrl)
    for key in ("AI_LLM_BASE_URL", "AI_EMBEDDING_BASE_URL"):
        value = values.get(key)
        if value:
            try:
                url_adapter.validate_python(value)
            except ValueError:
                errors.append(f"{key} must be an HTTP URL")

    timeout = values.get("AI_REQUEST_TIMEOUT_SECONDS")
    if timeout:
        try:
            if int(timeout) <= 0:
                raise ValueError
        except ValueError:
            errors.append("AI_REQUEST_TIMEOUT_SECONDS must be a positive integer")

    return EnvTemplateValidation(
        path=path,
        valid=not missing and not errors,
        missing_keys=missing,
        errors=tuple(errors),
    )


def load_settings_from_env_file(path: Path) -> Settings:
    template = validate_env_template(path)
    if not template.valid:
        details = "; ".join((*template.missing_keys, *template.errors))
        raise ValueError(f"invalid env file: {details}")

    values = dotenv_values(path)
    return Settings(
        llm_base_url=values["AI_LLM_BASE_URL"],  # type: ignore[arg-type]
        embedding_base_url=values["AI_EMBEDDING_BASE_URL"],  # type: ignore[arg-type]
        credential_file=Path(values["AI_CREDENTIAL_FILE"]),  # type: ignore[arg-type]
        llm_model=values["AI_LLM_MODEL"],  # type: ignore[arg-type]
        embedding_model=values["AI_EMBEDDING_MODEL"],  # type: ignore[arg-type]
        request_timeout_seconds=int(values["AI_REQUEST_TIMEOUT_SECONDS"]),  # type: ignore[arg-type]
    )
