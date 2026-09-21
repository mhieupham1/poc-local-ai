from __future__ import annotations

import asyncio
import hashlib
import hmac
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient


class AuthenticationError(ValueError):
    """Raised when a request cannot be authenticated."""


class AuthorizationError(ValueError):
    """Raised when an authenticated principal lacks a required role."""


@dataclass(frozen=True)
class Principal:
    actor_id: str
    roles: frozenset[str]
    tenant_id: str | None = None


class Authenticator(Protocol):
    async def authenticate(self, authorization: str | None) -> Principal: ...


def _bearer_token(header: str | None) -> str:
    if header is None:
        raise AuthenticationError("missing bearer token")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthenticationError("malformed bearer token")
    return parts[1]


@dataclass(frozen=True)
class StaticTokenAuth:
    _token: str
    _actor_id: str

    @classmethod
    def from_file(cls, path: Path) -> StaticTokenAuth:
        token = read_token_file(path)
        digest = hashlib.sha256(token.encode()).hexdigest()[:12]
        return cls(_token=token, _actor_id=f"service:{digest}")

    async def authenticate(self, authorization: str | None) -> Principal:
        candidate = _bearer_token(authorization)
        if not hmac.compare_digest(candidate, self._token):
            raise AuthenticationError("invalid bearer token")
        return Principal(
            actor_id=self._actor_id,
            roles=frozenset({"inference.user"}),
        )


def read_token_file(path: Path) -> str:
    """Read a token from a private file without accepting environment/argv secrets."""
    if not path.is_file():
        raise ValueError("token file does not exist or is not a regular file")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise ValueError(f"token file must have permission 0600, got {mode:04o}")
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("token must contain at least 32 characters")
    return token


@dataclass(frozen=True)
class OidcAuth:
    issuer: str
    audience: str
    required_role: str
    _jwks: PyJWKClient
    jwks_url: str = ""

    @classmethod
    def create(
        cls,
        *,
        issuer: str,
        audience: str,
        required_role: str,
        jwks_url: str | None = None,
    ) -> OidcAuth:
        normalized_issuer = issuer.rstrip("/")
        resolved_jwks_url = jwks_url or (f"{normalized_issuer}/protocol/openid-connect/certs")
        return cls(
            issuer=normalized_issuer,
            audience=audience,
            required_role=required_role,
            _jwks=PyJWKClient(
                resolved_jwks_url,
                cache_keys=True,
                lifespan=300,
            ),
            jwks_url=resolved_jwks_url,
        )

    async def authenticate(self, authorization: str | None) -> Principal:
        token = _bearer_token(authorization)
        try:
            signing_key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("invalid OIDC token") from exc

        realm_access = claims.get("realm_access", {})
        roles_value = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
        roles = frozenset(str(role) for role in roles_value if isinstance(role, str))
        if self.required_role not in roles:
            raise AuthorizationError("required role is missing")
        return Principal(
            actor_id=str(claims["sub"]),
            roles=roles,
            tenant_id=str(claims["tenant_id"]) if claims.get("tenant_id") else None,
        )
