from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from local_ai_lab.poc_b029.client import B029GatewayClient, GatewayClientError
from local_ai_lab.poc_b029.compare import compare_records
from local_ai_lab.poc_b029.documents import DocumentValidationError, document_to_data_url
from local_ai_lab.poc_b029.fixtures import generate_fixtures
from local_ai_lab.poc_b029.models import FIELD_ORDER, FieldName, KintoneProductionRecord
from local_ai_lab.poc_b029.report import B029ReportPaths, write_b029_reports
from local_ai_lab.poc_b029.retrieval import RetrievalError, rank_rules


class B029CommandError(ValueError):
    """Raised for safe-to-display B-029 command failures."""


class ExpectedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["match", "mismatch"]
    difference_fields: tuple[FieldName, ...]


class CaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    data_classification: Literal["synthetic"]
    label: str
    report_path: str | None = None
    report_png: str | None = None
    report_pdf: str | None = None
    kintone_record: KintoneProductionRecord
    rules: tuple[str, ...] = ()
    expected: ExpectedOutcome
    scenario: str


def generate_fixtures_command(output: Path) -> tuple[Path, ...]:
    return tuple(case.path for case in generate_fixtures(output))


def run_case_sync(
    *,
    case_path: Path,
    base_url: str,
    credential_file: Path,
    output: Path,
    timeout_seconds: float = 120.0,
) -> B029ReportPaths:
    return asyncio.run(
        run_case(
            case_path=case_path,
            base_url=base_url,
            credential_file=credential_file,
            output=output,
            timeout_seconds=timeout_seconds,
        )
    )


async def run_case(
    *,
    case_path: Path,
    base_url: str,
    credential_file: Path,
    output: Path,
    timeout_seconds: float,
) -> B029ReportPaths:
    manifest = _load_manifest(case_path)
    fixture_root = _fixture_root(case_path)
    document_path = _resolve_document_path(case_path, fixture_root, manifest)
    rules = _load_rules(manifest, fixture_root)
    image_data_url = document_to_data_url(document_path)
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
    ) as http_client:
        client = B029GatewayClient.from_credential_file(http_client, credential_file)
        vision = await client.extract_record(image_data_url=image_data_url)
        embedding = await client.embed_texts((_embedding_query(), *rules))
    comparison = compare_records(extracted=vision.record, expected=manifest.kintone_record)
    selected_rules = rank_rules(rules=rules, vectors=embedding.vectors)
    result = {
        "schema_version": "1.0",
        "case_id": manifest.case_id,
        "status": comparison.status,
        "missing_fields": list(comparison.missing_fields),
        "extracted_record": vision.record.model_dump(mode="json"),
        "kintone_record": manifest.kintone_record.model_dump(mode="json"),
        "differences": [
            difference.model_dump(mode="json") for difference in comparison.differences
        ],
        "selected_rules": [{"text": rule.text, "score": rule.score} for rule in selected_rules],
        "vision_model_id": vision.model_id,
        "vision_request_id": vision.request_id,
        "vision_e2e_seconds": vision.e2e_seconds,
        "embedding_model_id": embedding.model_id,
        "embedding_request_id": embedding.request_id,
        "embedding_e2e_seconds": embedding.e2e_seconds,
    }
    actual_difference_fields = [difference.field for difference in comparison.differences]
    evaluation = {
        "case_id": manifest.case_id,
        "expected_status": manifest.expected.status,
        "expected_difference_fields": list(manifest.expected.difference_fields),
        "actual_status": comparison.status,
        "actual_difference_fields": actual_difference_fields,
        "passed": (
            comparison.status == manifest.expected.status
            and actual_difference_fields == list(manifest.expected.difference_fields)
        ),
    }
    return write_b029_reports(output_dir=output, result=result, evaluation=evaluation)


def _load_manifest(case_path: Path) -> CaseManifest:
    if not case_path.is_file():
        raise B029CommandError("case manifest is not a regular file")
    try:
        raw = json.loads(case_path.read_text(encoding="utf-8"))
        return CaseManifest.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        raise B029CommandError("case manifest is invalid") from exc


def _fixture_root(case_path: Path) -> Path:
    return case_path.parent.parent if case_path.parent.name == "cases" else case_path.parent


def _resolve_document_path(
    case_path: Path,
    fixture_root: Path,
    manifest: CaseManifest,
) -> Path:
    relative = manifest.report_path or manifest.report_png
    if relative is None:
        raise B029CommandError("case manifest does not identify a report document")
    candidate = (case_path.parent / relative).resolve()
    if not candidate.is_relative_to(fixture_root.resolve()):
        raise B029CommandError("report document must remain inside fixture root")
    return candidate


def _load_rules(manifest: CaseManifest, fixture_root: Path) -> tuple[str, ...]:
    if manifest.rules:
        return manifest.rules
    source = fixture_root / "rules.synthetic.json"
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise B029CommandError("fixture rule file is unavailable") from exc
    raw_rules = document.get("rules") if isinstance(document, dict) else None
    if not isinstance(raw_rules, list):
        raise B029CommandError("fixture rule file is invalid")
    rules = tuple(
        item["text"]
        for item in raw_rules
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip()
    )
    if len(rules) != len(raw_rules):
        raise B029CommandError("fixture rule file is invalid")
    return rules


def _embedding_query() -> str:
    return "B-029 production report comparison: " + ", ".join(FIELD_ORDER)


def run_command_or_error(**kwargs: object) -> B029ReportPaths:
    try:
        return run_case_sync(**kwargs)  # type: ignore[arg-type]
    except (
        B029CommandError,
        DocumentValidationError,
        GatewayClientError,
        RetrievalError,
        OSError,
    ) as exc:
        raise B029CommandError(str(exc)) from exc
