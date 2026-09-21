from __future__ import annotations

import asyncio
import importlib
import stat
from pathlib import Path

import pytest


def _auth_module() -> object:
    try:
        return importlib.import_module("local_ai_lab.gateway.auth")
    except ModuleNotFoundError as exc:
        pytest.fail(f"gateway authentication is not implemented: {exc}")


def test_static_token_auth_accepts_only_matching_bearer_token(tmp_path: Path) -> None:
    auth = _auth_module()
    token_file = tmp_path / "gateway-token"
    token_file.write_text("a" * 48)
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    verifier = auth.StaticTokenAuth.from_file(token_file)  # type: ignore[attr-defined]
    principal = asyncio.run(verifier.authenticate(f"Bearer {'a' * 48}"))

    assert principal.actor_id.startswith("service:")
    assert principal.roles == frozenset({"inference.user"})
    with pytest.raises(auth.AuthenticationError):  # type: ignore[attr-defined]
        asyncio.run(verifier.authenticate(f"Bearer {'b' * 48}"))


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer one two"])
def test_static_token_auth_rejects_missing_or_malformed_header(
    tmp_path: Path, header: str | None
) -> None:
    auth = _auth_module()
    token_file = tmp_path / "gateway-token"
    token_file.write_text("z" * 48)
    token_file.chmod(0o600)
    verifier = auth.StaticTokenAuth.from_file(token_file)  # type: ignore[attr-defined]

    with pytest.raises(auth.AuthenticationError):  # type: ignore[attr-defined]
        asyncio.run(verifier.authenticate(header))


def test_static_token_auth_requires_private_non_placeholder_file(tmp_path: Path) -> None:
    auth = _auth_module()
    token_file = tmp_path / "gateway-token"
    token_file.write_text("replace-me")
    token_file.chmod(0o644)

    with pytest.raises(ValueError, match="0600"):
        auth.StaticTokenAuth.from_file(token_file)  # type: ignore[attr-defined]

    token_file.chmod(0o600)
    with pytest.raises(ValueError, match="at least 32"):
        auth.StaticTokenAuth.from_file(token_file)  # type: ignore[attr-defined]
