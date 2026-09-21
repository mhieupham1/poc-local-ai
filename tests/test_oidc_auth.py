from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from local_ai_lab.gateway.auth import AuthenticationError, AuthorizationError, OidcAuth


@dataclass(frozen=True)
class _SigningKey:
    key: object


class _Jwks:
    def __init__(self, public_key: object) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _: str) -> _SigningKey:
        return _SigningKey(self.public_key)


def _token(
    *, audience: str = "local-ai-gateway", roles: list[str] | None = None
) -> tuple[str, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    encoded = jwt.encode(
        {
            "iss": "https://identity.example/realms/local-ai",
            "aud": audience,
            "sub": "employee-001",
            "iat": now,
            "exp": now + 300,
            "tenant_id": "tenant-a",
            "realm_access": {"roles": roles or ["inference.user"]},
        },
        private_key,
        algorithm="RS256",
    )
    return encoded, private_key.public_key()


def test_oidc_auth_returns_actor_tenant_and_roles() -> None:
    token, public_key = _token()
    verifier = OidcAuth(
        issuer="https://identity.example/realms/local-ai",
        audience="local-ai-gateway",
        required_role="inference.user",
        _jwks=_Jwks(public_key),  # type: ignore[arg-type]
    )

    principal = asyncio.run(verifier.authenticate(f"Bearer {token}"))

    assert principal.actor_id == "employee-001"
    assert principal.tenant_id == "tenant-a"
    assert principal.roles == frozenset({"inference.user"})


def test_oidc_auth_rejects_wrong_audience_and_missing_role() -> None:
    wrong_audience, public_key = _token(audience="another-service")
    verifier = OidcAuth(
        issuer="https://identity.example/realms/local-ai",
        audience="local-ai-gateway",
        required_role="inference.user",
        _jwks=_Jwks(public_key),  # type: ignore[arg-type]
    )
    with pytest.raises(AuthenticationError):
        asyncio.run(verifier.authenticate(f"Bearer {wrong_audience}"))

    missing_role, public_key = _token(roles=["viewer"])
    verifier = OidcAuth(
        issuer="https://identity.example/realms/local-ai",
        audience="local-ai-gateway",
        required_role="inference.user",
        _jwks=_Jwks(public_key),  # type: ignore[arg-type]
    )
    with pytest.raises(AuthorizationError):
        asyncio.run(verifier.authenticate(f"Bearer {missing_role}"))


def test_oidc_auth_separates_public_issuer_from_private_jwks_endpoint() -> None:
    verifier = OidcAuth.create(
        issuer="http://127.0.0.1:8081/realms/local-ai",
        jwks_url="http://keycloak:8080/realms/local-ai/protocol/openid-connect/certs",
        audience="local-ai-gateway",
        required_role="inference.user",
    )

    assert verifier.issuer == "http://127.0.0.1:8081/realms/local-ai"
    assert verifier.jwks_url == (
        "http://keycloak:8080/realms/local-ai/protocol/openid-connect/certs"
    )
