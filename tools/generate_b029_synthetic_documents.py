#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate labelled synthetic reports for the B-029 technical demo."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Record:
    work_date: str
    work_order: str
    process: str
    item_code: str
    actual_quantity: int
    defect_quantity: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "work_date": self.work_date,
            "work_order": self.work_order,
            "process": self.process,
            "item_code": self.item_code,
            "actual_quantity": self.actual_quantity,
            "defect_quantity": self.defect_quantity,
        }


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    report: Record
    kintone: Record
    scenario: str

    @property
    def difference_fields(self) -> tuple[str, ...]:
        expected = self.kintone.as_dict()
        return tuple(
            field for field, value in self.report.as_dict().items() if value != expected[field]
        )

    @property
    def expected_status(self) -> str:
        return "match" if not self.difference_fields else "mismatch"


CASES: tuple[DemoCase, ...] = (
    DemoCase(
        "case-01",
        Record("2026-09-01", "WO-260901-001", "PRESS", "PRS-100-A", 1200, 2),
        Record("2026-09-01", "WO-260901-001", "PRESS", "PRS-100-A", 1200, 2),
        "baseline match — printed Press report",
    ),
    DemoCase(
        "case-02",
        Record("2026-09-02", "WO-260902-014", "WELD", "WLD-210-B", 780, 0),
        Record("2026-09-02", "WO-260902-014", "WELD", "WLD-210-B", 780, 0),
        "baseline match — printed Weld report",
    ),
    DemoCase(
        "case-03",
        Record("2026-09-03", "WO-260903-021", "PRESS", "PRS-330-C", 945, 5),
        Record("2026-09-03", "WO-260903-021", "PRESS", "PRS-330-C", 945, 5),
        "match with a non-zero defect quantity",
    ),
    DemoCase(
        "case-04",
        Record("2026-09-04", "WO-260904-008", "WELD", "WLD-450-A", 660, 1),
        Record("2026-09-04", "WO-260904-008", "WELD", "WLD-450-A", 660, 1),
        "match with a different work order",
    ),
    DemoCase(
        "case-05",
        Record("2026-09-05", "WO-260905-019", "PRESS", "PRS-520-D", 1500, 3),
        Record("2026-09-05", "WO-260905-019", "PRESS", "PRS-520-D", 1500, 3),
        "match at a higher quantity",
    ),
    DemoCase(
        "case-06",
        Record("2026-09-06", "WO-260906-004", "WELD", "WLD-110-A", 960, 1),
        Record("2026-09-06", "WO-260906-004", "WELD", "WLD-110-A", 1000, 1),
        "mismatch — actual quantity differs",
    ),
    DemoCase(
        "case-07",
        Record("2026-09-07", "WO-260907-011", "PRESS", "PRS-240-B", 840, 6),
        Record("2026-09-07", "WO-260907-011", "PRESS", "PRS-240-B", 840, 1),
        "mismatch — defect quantity differs",
    ),
    DemoCase(
        "case-08",
        Record("2026-09-08", "WO-260908-099", "WELD", "WLD-310-C", 700, 0),
        Record("2026-09-08", "WO-260908-009", "WELD", "WLD-310-C", 700, 0),
        "mismatch — work order differs by one digit",
    ),
    DemoCase(
        "case-09",
        Record("2026-09-09", "WO-260909-016", "PRESS", "PRS-710-X", 1110, 4),
        Record("2026-09-09", "WO-260909-016", "PRESS", "PRS-710-A", 1110, 4),
        "mismatch — item code differs",
    ),
    DemoCase(
        "case-10",
        Record("2026-09-10", "WO-260910-003", "WELD", "WLD-800-B", 530, 2),
        Record("2026-09-09", "WO-260910-003", "PRESS", "WLD-800-B", 530, 2),
        "mismatch — work date and process differ",
    ),
)

RULES = (
    {"id": "rule-01", "text": "Ngày sản xuất trên báo cáo giấy phải khớp bản ghi Kintone."},
    {"id": "rule-02", "text": "Mã lệnh sản xuất phải khớp tuyệt đối trước khi xác nhận."},
    {"id": "rule-03", "text": "Công đoạn PRESS hoặc WELD trên phiếu phải trùng bản ghi nguồn."},
    {"id": "rule-04", "text": "Mã hàng được đối chiếu sau khi chuẩn hóa khoảng trắng và chữ hoa."},
    {
        "id": "rule-05",
        "text": "Số lượng thực tế và lỗi là số nguyên không âm; chênh lệch cần kiểm tra.",
    },
    {
        "id": "rule-06",
        "text": "Không đọc được trường bắt buộc thì needs_human_review, không phải match.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("samples/b029"))
    return parser.parse_args()


def report_svg(demo_case: DemoCase) -> str:
    values = (
        ("WORK DATE", demo_case.report.work_date),
        ("WORK ORDER", demo_case.report.work_order),
        ("PROCESS", demo_case.report.process),
        ("ITEM CODE", demo_case.report.item_code),
        ("ACTUAL QUANTITY", f"{demo_case.report.actual_quantity:,}"),
        ("DEFECT QUANTITY", f"{demo_case.report.defect_quantity:,}"),
    )
    rows = "".join(
        f'<rect x="130" y="{440 + index * 115}" width="940" height="115" fill="#fbfbf7" stroke="#404348" stroke-width="2"/>'
        f'<text x="165" y="{485 + index * 115}" font-family="Arial, sans-serif" font-size="25" font-weight="700" fill="#33373d">{html.escape(label)}</text>'
        f'<text x="610" y="{520 + index * 115}" font-family="Arial, sans-serif" font-size="38" font-weight="700" fill="#101820">{html.escape(value)}</text>'
        for index, (label, value) in enumerate(values)
    )
    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"1750\" viewBox=\"0 0 1200 1750\">
  <rect width=\"1200\" height=\"1750\" fill=\"#d3d4d2\"/>
  <g transform=\"rotate(-0.35 600 875)\">
    <rect x=\"64\" y=\"56\" width=\"1072\" height=\"1638\" rx=\"7\" fill=\"#fdfdf8\" stroke=\"#8c8f90\" stroke-width=\"3\"/>
    <rect x=\"94\" y=\"88\" width=\"1012\" height=\"70\" fill=\"#cc4a35\"/>
    <text x=\"600\" y=\"136\" text-anchor=\"middle\" font-family=\"Arial, sans-serif\" font-size=\"31\" font-weight=\"700\" fill=\"#ffffff\">DEMO DATA — NOT PRODUCTION</text>
    <text x=\"600\" y=\"255\" text-anchor=\"middle\" font-family=\"Arial, sans-serif\" font-size=\"52\" font-weight=\"700\" fill=\"#101820\">DAILY PRODUCTION REPORT</text>
    <text x=\"600\" y=\"302\" text-anchor=\"middle\" font-family=\"Arial, sans-serif\" font-size=\"24\" fill=\"#48505a\">Synthetic printed form for Local AI Lab B-029 technical demonstration</text>
    <line x1=\"130\" y1=\"350\" x2=\"1070\" y2=\"350\" stroke=\"#404348\" stroke-width=\"3\"/>
    <text x=\"130\" y=\"399\" font-family=\"Arial, sans-serif\" font-size=\"25\" fill=\"#33373d\">REPORT ID: {demo_case.case_id.upper()}</text>
    <text x=\"800\" y=\"399\" font-family=\"Arial, sans-serif\" font-size=\"25\" fill=\"#33373d\">STATUS: PRINTED SAMPLE</text>
    {rows}
    <rect x=\"130\" y=\"1198\" width=\"940\" height=\"235\" fill=\"#f4f5f2\" stroke=\"#404348\" stroke-width=\"2\"/>
    <text x=\"165\" y=\"1250\" font-family=\"Arial, sans-serif\" font-size=\"25\" font-weight=\"700\" fill=\"#33373d\">OPERATOR NOTE</text>
    <text x=\"165\" y=\"1302\" font-family=\"Arial, sans-serif\" font-size=\"25\" fill=\"#33373d\">{html.escape(demo_case.scenario)}</text>
    <text x=\"165\" y=\"1360\" font-family=\"Arial, sans-serif\" font-size=\"22\" fill=\"#6a6f75\">No real person, factory, customer or production record is represented.</text>
    <line x1=\"130\" y1=\"1525\" x2=\"1070\" y2=\"1525\" stroke=\"#404348\" stroke-width=\"2\"/>
    <text x=\"130\" y=\"1575\" font-family=\"Arial, sans-serif\" font-size=\"21\" fill=\"#48505a\">Local AI Lab • B-029 • synthetic fixture</text>
    <text x=\"1070\" y=\"1575\" text-anchor=\"end\" font-family=\"Arial, sans-serif\" font-size=\"21\" fill=\"#48505a\">Page 1 of 1</text>
  </g>
</svg>
"""


def write_csv(path: Path, rows: list[dict[str, str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render(svg_path: Path, png_path: Path, pdf_path: Path) -> None:
    for file_format, destination in (("png", png_path), ("pdf", pdf_path)):
        subprocess.run(
            ["rsvg-convert", "--format", file_format, "--output", str(destination), str(svg_path)],
            check=True,
        )


def write_manifest(output: Path) -> None:
    digest_lines = []
    for file_path in sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    ):
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        digest_lines.append(f"{digest}  {file_path.relative_to(output)}")
    (output / "SHA256SUMS").write_text("\n".join(digest_lines) + "\n", encoding="utf-8")


def generate(output: Path) -> None:
    allowed_existing_names = {"README.md"}
    existing_names = {entry.name for entry in output.iterdir()} if output.exists() else set()
    unexpected_names = existing_names - allowed_existing_names
    if unexpected_names:
        raise ValueError(f"refusing to overwrite non-empty output directory: {output}")
    if shutil.which("rsvg-convert") is None:
        raise RuntimeError("rsvg-convert is required to generate PNG and PDF reports")

    reports = output / "reports"
    cases_directory = output / "cases"
    reports.mkdir(parents=True, exist_ok=True)
    cases_directory.mkdir(parents=True, exist_ok=True)
    kintone_rows: list[dict[str, str | int]] = []
    truth_rows: list[dict[str, str | int]] = []
    with tempfile.TemporaryDirectory(prefix="b029-svg-") as temporary:
        temporary_directory = Path(temporary)
        for demo_case in CASES:
            svg_path = temporary_directory / f"{demo_case.case_id}.svg"
            png_path = reports / f"{demo_case.case_id}.png"
            pdf_path = reports / f"{demo_case.case_id}.pdf"
            svg_path.write_text(report_svg(demo_case), encoding="utf-8")
            render(svg_path, png_path, pdf_path)
            document = {
                "case_id": demo_case.case_id,
                "data_classification": "synthetic",
                "label": "DEMO DATA — NOT PRODUCTION",
                "report_png": f"../reports/{demo_case.case_id}.png",
                "report_pdf": f"../reports/{demo_case.case_id}.pdf",
                "kintone_record": demo_case.kintone.as_dict(),
                "expected": {
                    "status": demo_case.expected_status,
                    "difference_fields": list(demo_case.difference_fields),
                },
                "scenario": demo_case.scenario,
            }
            (cases_directory / f"{demo_case.case_id}.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            kintone_rows.append({"case_id": demo_case.case_id, **demo_case.kintone.as_dict()})
            truth_rows.append(
                {
                    "case_id": demo_case.case_id,
                    "expected_status": demo_case.expected_status,
                    "difference_fields": ";".join(demo_case.difference_fields),
                    "scenario": demo_case.scenario,
                }
            )
    write_csv(output / "kintone-export.synthetic.csv", kintone_rows)
    write_csv(output / "ground-truth.synthetic.csv", truth_rows)
    (output / "rules.synthetic.json").write_text(
        json.dumps(
            {"label": "DEMO DATA — NOT PRODUCTION", "rules": RULES}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    write_manifest(output)


def main() -> None:
    arguments = parse_args()
    generate(arguments.output)
    print(f"generated {len(CASES)} synthetic B-029 cases in {arguments.output}")


if __name__ == "__main__":
    main()
