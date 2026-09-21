from __future__ import annotations

import json
from pathlib import Path

from local_ai_lab.cli import main
from local_ai_lab.poc_b029 import command
from local_ai_lab.poc_b029.client import EmbeddingResponse, ExtractionResponse
from local_ai_lab.poc_b029.fixtures import generate_fixtures
from local_ai_lab.poc_b029.models import ExtractedProductionRecord


def _credential_file(tmp_path: Path) -> Path:
    path = tmp_path / "gateway-token"
    path.write_text("z" * 32, encoding="utf-8")
    path.chmod(0o600)
    return path


class _MatchingGateway:
    @classmethod
    def from_credential_file(cls, *_args: object, **_kwargs: object) -> _MatchingGateway:
        return cls()

    async def extract_record(self, *, image_data_url: str) -> ExtractionResponse:
        assert image_data_url.startswith("data:image/png;base64,")
        return ExtractionResponse(
            record=ExtractedProductionRecord(
                work_date="2026-09-01",
                work_order="WO-260901-001",
                process="PRESS",
                item_code="PRS-100-A",
                actual_quantity=1200,
                defect_quantity=2,
            ),
            request_id="vision-request-id",
            model_id="vision-model",
            e2e_seconds=0.2,
        )

    async def embed_texts(self, _texts: tuple[str, ...]) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=(
                (1.0, 0.0),
                (0.9, 0.1),
                (0.1, 0.9),
                (0.5, 0.5),
                (0.2, 0.8),
                (0.8, 0.2),
                (0.7, 0.3),
            ),
            request_id="embedding-request-id",
            model_id="embedding-model",
            e2e_seconds=0.1,
        )


class _IncompleteGateway(_MatchingGateway):
    async def extract_record(self, *, image_data_url: str) -> ExtractionResponse:
        return ExtractionResponse(
            record=ExtractedProductionRecord(
                work_date=None,
                work_order=None,
                process=None,
                item_code=None,
                actual_quantity=None,
                defect_quantity=None,
            ),
            request_id="vision-request-id",
            model_id="vision-model",
            e2e_seconds=0.2,
        )


def test_run_writes_sanitized_result_evaluation_and_markdown(
    tmp_path: Path, monkeypatch: object
) -> None:
    generated = generate_fixtures(tmp_path / "fixtures")
    output = tmp_path / "report"
    monkeypatch.setattr(command, "B029GatewayClient", _MatchingGateway)  # type: ignore[attr-defined]

    exit_code = main(
        [
            "poc",
            "b029",
            "run",
            "--case",
            str(generated[0].path),
            "--base-url",
            "https://gateway.example",
            "--credential-file",
            str(_credential_file(tmp_path)),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    evaluation = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert result["status"] == "match"
    assert result["vision_request_id"] == "vision-request-id"
    assert result["embedding_request_id"] == "embedding-request-id"
    assert evaluation["passed"] is True
    assert "data:image" not in combined
    assert "c2FmZS1maXh0dXJl" not in combined
    assert "z" * 32 not in combined


def test_run_writes_human_review_as_a_valid_business_outcome(
    tmp_path: Path, monkeypatch: object
) -> None:
    generated = generate_fixtures(tmp_path / "fixtures")
    output = tmp_path / "report"
    monkeypatch.setattr(command, "B029GatewayClient", _IncompleteGateway)  # type: ignore[attr-defined]

    exit_code = main(
        [
            "poc",
            "b029",
            "run",
            "--case",
            str(generated[0].path),
            "--base-url",
            "https://gateway.example",
            "--credential-file",
            str(_credential_file(tmp_path)),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "needs_human_review"
    assert "human review required" in (output / "result.md").read_text(encoding="utf-8")


def test_run_rejects_document_path_outside_fixture_root(
    tmp_path: Path, monkeypatch: object
) -> None:
    generated = generate_fixtures(tmp_path / "fixtures")
    case_document = json.loads(generated[0].path.read_text(encoding="utf-8"))
    case_document["report_path"] = "../outside.png"
    generated[0].path.write_text(json.dumps(case_document), encoding="utf-8")
    monkeypatch.setattr(command, "B029GatewayClient", _MatchingGateway)  # type: ignore[attr-defined]
    output = tmp_path / "report"

    exit_code = main(
        [
            "poc",
            "b029",
            "run",
            "--case",
            str(generated[0].path),
            "--base-url",
            "https://gateway.example",
            "--credential-file",
            str(_credential_file(tmp_path)),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    assert not output.exists()


def test_fixtures_command_creates_a_reusable_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "generated"

    exit_code = main(["poc", "b029", "fixtures", "--output", str(output)])

    assert exit_code == 0
    assert len(list(output.glob("case-*.json"))) == 10
