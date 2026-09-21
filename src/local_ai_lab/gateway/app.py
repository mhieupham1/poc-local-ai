from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from pydantic import AnyHttpUrl, PositiveFloat, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.background import BackgroundTask

from local_ai_lab.gateway.auth import (
    AuthenticationError,
    Authenticator,
    AuthorizationError,
    OidcAuth,
    StaticTokenAuth,
)


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", extra="forbid")

    auth_mode: Literal["token", "oidc"] = "token"
    token_file: Path = Path("/run/secrets/gateway_token")
    llm_url: AnyHttpUrl = AnyHttpUrl("http://llm:8000")
    embedding_url: AnyHttpUrl = AnyHttpUrl("http://embedding:80")
    request_timeout_seconds: PositiveFloat = 120
    max_body_bytes: PositiveInt = 10 * 1024 * 1024
    max_concurrency: PositiveInt = 8
    queue_timeout_seconds: PositiveFloat = 5.0
    oidc_issuer: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8081/realms/local-ai")
    oidc_jwks_url: AnyHttpUrl = AnyHttpUrl(
        "http://keycloak:8080/realms/local-ai/protocol/openid-connect/certs"
    )
    oidc_audience: str = "local-ai-gateway"
    required_role: str = "inference.user"
    allowed_media_domains: str = "qianwen-res.oss-cn-beijing.aliyuncs.com"

    @field_validator("llm_url", "embedding_url")
    @classmethod
    def require_private_upstream(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        host = value.host or ""
        is_loopback = host in {"localhost", "127.0.0.1", "::1"}
        is_compose_service = "." not in host and ":" not in host and host.replace("-", "").isalnum()
        if not (is_loopback or is_compose_service):
            raise ValueError("model upstream must use a private service name or loopback")
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("model upstream URL must not contain credentials or query data")
        return value

    @property
    def media_domains(self) -> frozenset[str]:
        return frozenset(
            domain.strip().lower()
            for domain in self.allowed_media_domains.split(",")
            if domain.strip()
        )


async def _read_limited_body(request: Request, limit: int) -> bytes | None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                return None
        except ValueError:
            return None
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _media_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        image_url = value.get("image_url")
        if isinstance(image_url, str):
            urls.append(image_url)
        elif isinstance(image_url, dict) and isinstance(image_url.get("url"), str):
            urls.append(image_url["url"])
        for key, child in value.items():
            if key != "image_url":
                urls.extend(_media_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(_media_urls(child))
    return urls


def _contains_unapproved_media(body: bytes, allowed_domains: frozenset[str]) -> bool:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    for url in _media_urls(payload):
        if url.startswith("data:image/"):
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_domains:
            return True
        if parsed.username or parsed.password:
            return True
    return False


class GatewayMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "local_ai_gateway_requests_total",
            "Gateway requests by route and status.",
            ("route", "status"),
            registry=self.registry,
        )
        self.upstream_seconds = Histogram(
            "local_ai_gateway_upstream_seconds",
            "Gateway upstream response time.",
            ("route",),
            registry=self.registry,
        )
        self.inflight = Gauge(
            "local_ai_gateway_inflight_requests",
            "Requests currently consuming an inference slot.",
            registry=self.registry,
        )
        self.rejections = Counter(
            "local_ai_gateway_rejections_total",
            "Authentication, authorization, size, and queue rejections.",
            ("reason",),
            registry=self.registry,
        )


def _authenticator(settings: GatewaySettings) -> Authenticator:
    if settings.auth_mode == "token":
        return StaticTokenAuth.from_file(settings.token_file)
    return OidcAuth.create(
        issuer=str(settings.oidc_issuer),
        jwks_url=str(settings.oidc_jwks_url),
        audience=settings.oidc_audience,
        required_role=settings.required_role,
    )


def create_app(
    settings: GatewaySettings,
    *,
    authenticator: Authenticator | None = None,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    auth = authenticator or _authenticator(settings)
    metrics = GatewayMetrics()
    slots = asyncio.Semaphore(settings.max_concurrency)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        transport=upstream_transport,
        follow_redirects=False,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    app = FastAPI(
        title="Local AI Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    async def require_principal(authorization: str | None) -> None:
        try:
            await auth.authenticate(authorization)
        except AuthenticationError as exc:
            metrics.rejections.labels(reason="authentication").inc()
            raise HTTPException(status_code=401, detail="authentication required") from exc
        except AuthorizationError as exc:
            metrics.rejections.labels(reason="authorization").inc()
            raise HTTPException(status_code=403, detail="required role is missing") from exc

    route_targets = {
        "/v1/chat/completions": (str(settings.llm_url).rstrip("/"), "/v1/chat/completions"),
        "/v1/models": (str(settings.llm_url).rstrip("/"), "/v1/models"),
        "/v1/embeddings": (
            str(settings.embedding_url).rstrip("/"),
            "/v1/embeddings",
        ),
    }

    async def proxy(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        await require_principal(authorization)
        body = await _read_limited_body(request, settings.max_body_bytes)
        if body is None:
            metrics.rejections.labels(reason="body_too_large").inc()
            return JSONResponse(status_code=413, content={"detail": "request body too large"})
        if request.url.path == "/v1/chat/completions" and _contains_unapproved_media(
            body, settings.media_domains
        ):
            metrics.rejections.labels(reason="media_url").inc()
            return JSONResponse(
                status_code=400,
                content={"detail": "remote media URL is not allowed"},
            )
        try:
            await asyncio.wait_for(slots.acquire(), timeout=settings.queue_timeout_seconds)
        except TimeoutError:
            metrics.rejections.labels(reason="queue_full").inc()
            return JSONResponse(status_code=429, content={"detail": "inference queue is full"})

        metrics.inflight.inc()
        released = False

        def release_slot() -> None:
            nonlocal released
            if not released:
                slots.release()
                metrics.inflight.dec()
                released = True

        route = request.url.path
        base_url, upstream_path = route_targets[route]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        headers = {
            "accept": request.headers.get("accept", "application/json"),
            "content-type": request.headers.get("content-type", "application/json"),
            "x-request-id": request_id,
        }
        started = time.monotonic()
        try:
            upstream_request = client.build_request(
                request.method,
                f"{base_url}{upstream_path}",
                headers=headers,
                content=body,
            )
            upstream = await client.send(upstream_request, stream=True)
        except httpx.TimeoutException:
            release_slot()
            metrics.requests.labels(route=route, status="504").inc()
            return JSONResponse(status_code=504, content={"detail": "upstream timed out"})
        except httpx.HTTPError:
            release_slot()
            metrics.requests.labels(route=route, status="502").inc()
            return JSONResponse(status_code=502, content={"detail": "upstream unavailable"})
        except BaseException:
            release_slot()
            raise

        metrics.upstream_seconds.labels(route=route).observe(time.monotonic() - started)
        metrics.requests.labels(route=route, status=str(upstream.status_code)).inc()

        async def cleanup() -> None:
            try:
                await upstream.aclose()
            finally:
                release_slot()

        async def response_body() -> AsyncIterator[bytes]:
            try:
                if upstream.is_stream_consumed:
                    yield upstream.content
                    return
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                try:
                    await upstream.aclose()
                finally:
                    release_slot()

        content_type = upstream.headers.get("content-type", "application/octet-stream")
        return StreamingResponse(
            response_body(),
            status_code=upstream.status_code,
            headers={"content-type": content_type, "x-request-id": request_id},
            background=BackgroundTask(cleanup),
        )

    for path in route_targets:
        methods = ["GET"] if path == "/v1/models" else ["POST"]
        app.add_api_route(path, proxy, methods=methods, include_in_schema=False)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, object]:
        return {"status": "ok", "auth_mode": settings.auth_mode}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> Response:
        readiness: dict[str, bool] = {}
        for name, base_url in (
            ("llm", str(settings.llm_url).rstrip("/")),
            ("embedding", str(settings.embedding_url).rstrip("/")),
        ):
            try:
                response = await client.get(f"{base_url}/health")
                readiness[name] = response.is_success
            except httpx.HTTPError:
                readiness[name] = False
        ready = all(readiness.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "upstreams": readiness,
            },
        )

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(metrics.registry), media_type="text/plain; version=0.0.4")

    return app


def create_app_from_env() -> FastAPI:
    return create_app(GatewaySettings())
