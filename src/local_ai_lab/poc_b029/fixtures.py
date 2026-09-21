from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from local_ai_lab.poc_b029.models import FIELD_ORDER, FieldName, KintoneProductionRecord

DEMO_LABEL = "DEMO DATA — NOT PRODUCTION"


@dataclass(frozen=True)
class FixtureExpected:
    status: str
    difference_fields: tuple[FieldName, ...]


@dataclass(frozen=True)
class GeneratedFixture:
    path: Path
    expected: FixtureExpected
    rendered_text: str


@dataclass(frozen=True)
class FixtureDefinition:
    case_id: str
    report: dict[str, str | int]
    kintone: dict[str, str | int]
    scenario: str

    @property
    def expected(self) -> FixtureExpected:
        differences = tuple(
            field for field in FIELD_ORDER if self.report[field] != self.kintone[field]
        )
        return FixtureExpected("mismatch" if differences else "match", differences)


def _record(
    work_date: str,
    work_order: str,
    process: str,
    item_code: str,
    actual_quantity: int,
    defect_quantity: int,
) -> dict[str, str | int]:
    return {
        "work_date": work_date,
        "work_order": work_order,
        "process": process,
        "item_code": item_code,
        "actual_quantity": actual_quantity,
        "defect_quantity": defect_quantity,
    }


FIXTURES: tuple[FixtureDefinition, ...] = (
    FixtureDefinition(
        "case-01",
        _record("2026-09-01", "WO-260901-001", "PRESS", "PRS-100-A", 1200, 2),
        _record("2026-09-01", "WO-260901-001", "PRESS", "PRS-100-A", 1200, 2),
        "baseline match — printed Press report",
    ),
    FixtureDefinition(
        "case-02",
        _record("2026-09-02", "WO-260902-014", "WELD", "WLD-210-B", 780, 0),
        _record("2026-09-02", "WO-260902-014", "WELD", "WLD-210-B", 780, 0),
        "baseline match — printed Weld report",
    ),
    FixtureDefinition(
        "case-03",
        _record("2026-09-03", "WO-260903-021", "PRESS", "PRS-330-C", 945, 5),
        _record("2026-09-03", "WO-260903-021", "PRESS", "PRS-330-C", 945, 5),
        "match with a non-zero defect quantity",
    ),
    FixtureDefinition(
        "case-04",
        _record("2026-09-04", "WO-260904-008", "WELD", "WLD-450-A", 660, 1),
        _record("2026-09-04", "WO-260904-008", "WELD", "WLD-450-A", 660, 1),
        "match with a different work order",
    ),
    FixtureDefinition(
        "case-05",
        _record("2026-09-05", "WO-260905-019", "PRESS", "PRS-520-D", 1500, 3),
        _record("2026-09-05", "WO-260905-019", "PRESS", "PRS-520-D", 1500, 3),
        "match at a higher quantity",
    ),
    FixtureDefinition(
        "case-06",
        _record("2026-09-06", "WO-260906-004", "WELD", "WLD-110-A", 960, 1),
        _record("2026-09-06", "WO-260906-004", "WELD", "WLD-110-A", 1000, 1),
        "mismatch — actual quantity differs",
    ),
    FixtureDefinition(
        "case-07",
        _record("2026-09-07", "WO-260907-011", "PRESS", "PRS-240-B", 840, 6),
        _record("2026-09-07", "WO-260907-011", "PRESS", "PRS-240-B", 840, 1),
        "mismatch — defect quantity differs",
    ),
    FixtureDefinition(
        "case-08",
        _record("2026-09-08", "WO-260908-099", "WELD", "WLD-310-C", 700, 0),
        _record("2026-09-08", "WO-260908-009", "WELD", "WLD-310-C", 700, 0),
        "mismatch — work order differs by one digit",
    ),
    FixtureDefinition(
        "case-09",
        _record("2026-09-09", "WO-260909-016", "PRESS", "PRS-710-X", 1110, 4),
        _record("2026-09-09", "WO-260909-016", "PRESS", "PRS-710-A", 1110, 4),
        "mismatch — item code differs",
    ),
    FixtureDefinition(
        "case-10",
        _record("2026-09-10", "WO-260910-003", "WELD", "WLD-800-B", 530, 2),
        _record("2026-09-09", "WO-260910-003", "PRESS", "WLD-800-B", 530, 2),
        "mismatch — work date and process differ",
    ),
)

RULES = (
    "Ngày sản xuất trên báo cáo giấy phải khớp bản ghi Kintone.",
    "Mã lệnh sản xuất phải khớp tuyệt đối trước khi xác nhận.",
    "Công đoạn PRESS hoặc WELD trên phiếu phải trùng bản ghi nguồn.",
    "Mã hàng được đối chiếu sau khi chuẩn hóa khoảng trắng và chữ hoa.",
    "Số lượng thực tế và lỗi là số nguyên không âm; chênh lệch cần kiểm tra.",
    "Không đọc được trường bắt buộc thì needs_human_review, không phải match.",
)


def generate_fixtures(output: Path) -> tuple[GeneratedFixture, ...]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("fixture output directory must be empty")
    reports = output / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    generated: list[GeneratedFixture] = []
    for fixture in FIXTURES:
        report_path = reports / f"{fixture.case_id}.png"
        rendered_text = _render_report(report_path, fixture)
        case_path = output / f"{fixture.case_id}.json"
        document = {
            "case_id": fixture.case_id,
            "data_classification": "synthetic",
            "label": DEMO_LABEL,
            "report_path": str(report_path.relative_to(output)),
            "kintone_record": KintoneProductionRecord.model_validate(fixture.kintone).model_dump(
                mode="json"
            ),
            "rules": list(RULES),
            "expected": {
                "status": fixture.expected.status,
                "difference_fields": list(fixture.expected.difference_fields),
            },
            "scenario": fixture.scenario,
        }
        case_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        generated.append(GeneratedFixture(case_path, fixture.expected, rendered_text))
    return tuple(generated)


def _render_report(destination: Path, fixture: FixtureDefinition) -> str:
    image = Image.new("RGB", (1200, 1600), "#fdfdf8")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((70, 60, 1130, 120), fill="#cc4a35")
    draw.text((360, 82), "DEMO DATA - NOT PRODUCTION", fill="white", font=font)
    draw.text((410, 190), "DAILY PRODUCTION REPORT", fill="#101820", font=font)
    draw.text((90, 270), f"REPORT ID: {fixture.case_id.upper()}", fill="#33373d", font=font)
    labels = (
        ("WORK DATE", fixture.report["work_date"]),
        ("WORK ORDER", fixture.report["work_order"]),
        ("PROCESS", fixture.report["process"]),
        ("ITEM CODE", fixture.report["item_code"]),
        ("ACTUAL QUANTITY", fixture.report["actual_quantity"]),
        ("DEFECT QUANTITY", fixture.report["defect_quantity"]),
    )
    for index, (label, value) in enumerate(labels):
        top = 340 + index * 130
        draw.rectangle((90, top, 1110, top + 110), outline="#404348", width=3)
        draw.text((120, top + 28), label, fill="#33373d", font=font)
        draw.text((600, top + 28), str(value), fill="#101820", font=font)
    draw.text((90, 1210), fixture.scenario, fill="#48505a", font=font)
    draw.text((90, 1510), "Local AI Lab B-029 synthetic fixture", fill="#48505a", font=font)
    image.save(destination, format="PNG", optimize=True)
    return f"{DEMO_LABEL}\n{fixture.scenario}"
