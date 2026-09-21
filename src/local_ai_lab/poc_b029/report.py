from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class B029ReportPaths:
    result_json: Path
    result_markdown: Path
    evaluation_json: Path


def write_b029_reports(
    *,
    output_dir: Path,
    result: dict[str, Any],
    evaluation: dict[str, Any],
) -> B029ReportPaths:
    """Atomically publish report-only artifacts into a new output directory."""
    if output_dir.exists():
        raise ValueError("output directory already exists")
    _ensure_safe(result)
    _ensure_safe(evaluation)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".b029-", dir=output_dir.parent) as temporary:
        temporary_dir = Path(temporary)
        paths = B029ReportPaths(
            result_json=temporary_dir / "result.json",
            result_markdown=temporary_dir / "result.md",
            evaluation_json=temporary_dir / "evaluation.json",
        )
        _atomic_write(paths.result_json, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        _atomic_write(
            paths.evaluation_json, json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n"
        )
        _atomic_write(paths.result_markdown, _markdown(result, evaluation))
        temporary_dir.replace(output_dir)
    return B029ReportPaths(
        result_json=output_dir / "result.json",
        result_markdown=output_dir / "result.md",
        evaluation_json=output_dir / "evaluation.json",
    )


def _ensure_safe(document: dict[str, Any]) -> None:
    rendered = json.dumps(document, ensure_ascii=False)
    if "data:image" in rendered or "base64" in rendered:
        raise ValueError("report cannot contain source document content")


def _markdown(result: dict[str, Any], evaluation: dict[str, Any]) -> str:
    status = str(result["status"])
    review_notice = "\n**human review required**\n" if status == "needs_human_review" else ""
    differences = result["differences"]
    difference_rows = (
        "".join(
            "| {field} | {report_value} | {kintone_value} | {reason} |\n".format(
                field=item["field"],
                report_value=item["report_value"],
                kintone_value=item["kintone_value"],
                reason=item["reason"],
            )
            for item in differences
        )
        or "| — | — | — | no differences |\n"
    )
    rule_rows = "".join(
        f"| {item['text']} | {item['score']:.4f} |\n" for item in result["selected_rules"]
    )
    return (
        "# B-029 comparison result\n\n"
        f"- Case: `{result['case_id']}`\n"
        f"- Status: `{status}`\n"
        f"- Evaluation passed: `{evaluation['passed']}`\n"
        f"- Vision request: `{result['vision_request_id']}`\n"
        f"- Embedding request: `{result['embedding_request_id']}`\n"
        f"{review_notice}\n"
        "## Differences\n\n"
        "| Field | Report | Kintone | Reason |\n"
        "|---|---|---|---|\n"
        f"{difference_rows}\n"
        "## Selected rules\n\n"
        "| Rule | Cosine score |\n"
        "|---|---:|\n"
        f"{rule_rows}"
    )


def _atomic_write(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
