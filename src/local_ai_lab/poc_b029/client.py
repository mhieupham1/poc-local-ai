from __future__ import annotations

import json
import math
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, ValidationError

from local_ai_lab.gateway.auth import read_token_file
from local_ai_lab.poc_b029.models import (
    FIELD_ORDER,
    ExtractedProductionRecord,
    FieldName,
)

# This is the OpenAI-compatible name exposed by vLLM, not the Hugging Face ID.
DEFAULT_VISION_MODEL = "local-vision-language"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


class GatewayClientError(RuntimeError):
    """Raised without retaining credential, document or raw upstream response data."""


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: ExtractedProductionRecord
    request_id: str
    model_id: str
    e2e_seconds: NonNegativeFloat


class EmbeddingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vectors: tuple[tuple[float, ...], ...]
    request_id: str
    model_id: str
    e2e_seconds: NonNegativeFloat


class B029GatewayClient:
    """Narrow client for the existing gateway; it never exposes raw responses."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        credential: str,
        *,
        vision_model: str = DEFAULT_VISION_MODEL,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._http_client = http_client
        self._credential = credential
        self._vision_model = vision_model
        self._embedding_model = embedding_model

    @classmethod
    def from_credential_file(
        cls,
        http_client: httpx.AsyncClient,
        credential_file: Path,
        *,
        vision_model: str = DEFAULT_VISION_MODEL,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> B029GatewayClient:
        return cls(
            http_client,
            read_token_file(credential_file),
            vision_model=vision_model,
            embedding_model=embedding_model,
        )

    async def extract_record(self, *, image_data_url: str) -> ExtractionResponse:
        document, request_id, elapsed = await self._post(
            "/v1/chat/completions",
            {
                "model": self._vision_model,
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "production_report",
                        "strict": True,
                        "schema": ExtractedProductionRecord.model_json_schema(),
                    },
                },
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract only the requested production-report fields. "
                            "Use null when a field cannot be read."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Return JSON with work_date, work_order, process, item_code, "
                                    "actual_quantity, defect_quantity."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    },
                ],
            },
        )
        content = _chat_content(document)
        try:
            structured = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GatewayClientError("vision response is not valid structured JSON") from exc
        record = _record_or_human_review(structured)
        model_id = _model_id(document, self._vision_model)
        return ExtractionResponse(
            record=record,
            request_id=request_id,
            model_id=model_id,
            e2e_seconds=elapsed,
        )

    async def embed_texts(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        if not texts or any(not text.strip() for text in texts):
            raise GatewayClientError("embedding input must contain non-empty text")
        document, request_id, elapsed = await self._post(
            "/v1/embeddings",
            {"model": self._embedding_model, "input": list(texts)},
        )
        vectors = _embedding_vectors(document, len(texts))
        return EmbeddingResponse(
            vectors=vectors,
            request_id=request_id,
            model_id=_model_id(document, self._embedding_model),
            e2e_seconds=elapsed,
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str, float]:
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await self._http_client.post(
                path,
                headers={
                    "authorization": f"Bearer {self._credential}",
                    "x-request-id": request_id,
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise GatewayClientError("gateway request timed out") from exc
        except httpx.HTTPError as exc:
            raise GatewayClientError("gateway request failed") from exc
        elapsed = max(time.monotonic() - started, 0.0)
        if response.status_code < 200 or response.status_code >= 300:
            raise GatewayClientError(f"gateway returned HTTP {response.status_code}")
        try:
            document = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise GatewayClientError("gateway response is not valid JSON") from exc
        if not isinstance(document, dict):
            raise GatewayClientError("gateway response must be a JSON object")
        return document, response.headers.get("x-request-id", request_id), elapsed


def _chat_content(document: dict[str, Any]) -> str:
    choices = document.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise GatewayClientError("vision response contains no single choice")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise GatewayClientError("vision response contains no structured content")
    return content


def _record_or_human_review(value: object) -> ExtractedProductionRecord:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GatewayClientError("vision response does not contain an object record")
    unexpected = set(value) - set(FIELD_ORDER)
    if unexpected:
        raise GatewayClientError("vision response contains unsupported record fields")
    normalized: dict[FieldName, object] = {
        field: _usable_field_value(field, value.get(field)) for field in FIELD_ORDER
    }
    try:
        return ExtractedProductionRecord.model_validate(normalized)
    except ValidationError as exc:
        raise GatewayClientError("vision response does not match record schema") from exc


def _usable_field_value(field: FieldName, value: object) -> str | int | None:
    if value is None:
        return None
    if field == "work_date":
        if not isinstance(value, str):
            return None
        try:
            date.fromisoformat(value)
        except ValueError:
            return None
        return value
    if field in {"actual_quantity", "defect_quantity"}:
        return (
            value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        )
    return value if isinstance(value, str) and value.strip() else None


def _embedding_vectors(
    document: dict[str, Any], expected_count: int
) -> tuple[tuple[float, ...], ...]:
    data = document.get("data")
    if not isinstance(data, list) or len(data) != expected_count:
        raise GatewayClientError("embedding response has an unexpected vector count")
    vectors: list[tuple[float, ...]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict) or item.get("index") != index:
            raise GatewayClientError("embedding response has invalid vector ordering")
        raw_vector = item.get("embedding")
        if not isinstance(raw_vector, list) or not raw_vector:
            raise GatewayClientError("embedding response has an invalid vector")
        vector = tuple(_finite_number(component) for component in raw_vector)
        vectors.append(vector)
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise GatewayClientError("embedding response vectors have inconsistent dimensions")
    return tuple(vectors)


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GatewayClientError("embedding response has a non-numeric vector")
    number = float(value)
    if not math.isfinite(number):
        raise GatewayClientError("embedding response has a non-finite vector")
    return number


def _model_id(document: dict[str, Any], fallback: str) -> str:
    model = document.get("model")
    return model if isinstance(model, str) and model else fallback
