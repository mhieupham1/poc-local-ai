from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class StackValidation(BaseModel):
    valid: bool
    errors: tuple[str, ...]
    published_ports: dict[str, tuple[str, ...]]


_COMPOSE_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)}")


def _expand_compose_defaults(value: str, environment: dict[str, str]) -> str:
    return _COMPOSE_DEFAULT.sub(
        lambda match: environment.get(match.group(1), match.group(2)),
        value,
    )


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ValueError(f"env file line {line_number} must contain KEY=VALUE")
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"env file line {line_number} has an invalid key")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _port_text(port: object, environment: dict[str, str]) -> str:
    if isinstance(port, str | int):
        return _expand_compose_defaults(str(port), environment)
    if isinstance(port, dict):
        host_ip = str(port.get("host_ip", ""))
        published = str(port.get("published", ""))
        target = str(port.get("target", ""))
        prefix = f"{host_ip}:" if host_ip else ""
        return f"{prefix}{published}:{target}"
    raise ValueError(f"unsupported port entry: {port!r}")


def validate_compose(path: Path, *, env_file: Path | None = None) -> StackValidation:
    if not path.is_file():
        return StackValidation(
            valid=False, errors=(f"compose file does not exist: {path}",), published_ports={}
        )
    environment: dict[str, str] = {}
    if env_file is not None:
        if not env_file.is_file():
            return StackValidation(
                valid=False,
                errors=(f"env file does not exist: {env_file}",),
                published_ports={},
            )
        try:
            environment.update(_read_env_file(env_file))
        except ValueError as exc:
            return StackValidation(valid=False, errors=(str(exc),), published_ports={})
    environment.update(os.environ)
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        return StackValidation(
            valid=False, errors=("compose file must define services",), published_ports={}
        )

    services: dict[str, Any] = document["services"]
    errors: list[str] = []
    published_ports: dict[str, tuple[str, ...]] = {}
    for name, service in services.items():
        if not isinstance(service, dict):
            errors.append(f"service {name} must be a mapping")
            continue
        ports = tuple(_port_text(port, environment) for port in service.get("ports", ()))
        if ports:
            published_ports[str(name)] = ports
        if name in {"llm", "embedding", "dcgm-exporter"} and ports:
            errors.append(f"service {name} must not publish a host port")
        for port in ports:
            if not port.startswith("127.0.0.1:"):
                errors.append(f"service {name} publishes non-loopback port {port}")
        image = service.get("image")
        if isinstance(image, str):
            resolved_image = _expand_compose_defaults(image, environment)
            image_name = resolved_image.rsplit("/", maxsplit=1)[-1]
            if resolved_image.endswith(":latest") or (
                ":" not in image_name and "@sha256:" not in resolved_image
            ):
                errors.append(f"service {name} must not use a mutable latest image")

    required = {"llm", "embedding", "gateway", "prometheus", "grafana", "dcgm-exporter"}
    missing = sorted(required - set(services))
    errors.extend(f"required service is missing: {name}" for name in missing)
    return StackValidation(
        valid=not errors,
        errors=tuple(errors),
        published_ports=published_ports,
    )
