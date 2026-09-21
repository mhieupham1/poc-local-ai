from __future__ import annotations

from datetime import date

from local_ai_lab.poc_b029.compare import compare_records
from local_ai_lab.poc_b029.models import (
    ExtractedProductionRecord,
    KintoneProductionRecord,
)


def _kintone_record() -> KintoneProductionRecord:
    return KintoneProductionRecord(
        work_date=date(2026, 9, 21),
        work_order="WO-001",
        process="PRESS",
        item_code="AB-01",
        actual_quantity=120,
        defect_quantity=2,
    )


def test_compare_normalizes_identifiers_before_declaring_match() -> None:
    result = compare_records(
        extracted=ExtractedProductionRecord(
            work_date="2026-09-21",
            work_order=" wo-001 ",
            process="press",
            item_code=" ab-01 ",
            actual_quantity=120,
            defect_quantity=2,
        ),
        expected=_kintone_record(),
    )

    assert result.status == "match"
    assert result.differences == ()


def test_compare_returns_each_different_field() -> None:
    result = compare_records(
        extracted=ExtractedProductionRecord(
            work_date="2026-09-20",
            work_order="WO-001",
            process="WELD",
            item_code="AB-01",
            actual_quantity=119,
            defect_quantity=2,
        ),
        expected=_kintone_record(),
    )

    assert result.status == "mismatch"
    assert [difference.field for difference in result.differences] == [
        "work_date",
        "process",
        "actual_quantity",
    ]


def test_compare_requires_human_review_when_vision_field_is_missing() -> None:
    result = compare_records(
        extracted=ExtractedProductionRecord(
            work_date="2026-09-21",
            work_order=None,
            process="PRESS",
            item_code="AB-01",
            actual_quantity=120,
            defect_quantity=2,
        ),
        expected=_kintone_record(),
    )

    assert result.status == "needs_human_review"
    assert result.differences == ()
    assert result.missing_fields == ("work_order",)


def test_compare_requires_human_review_when_vision_quantity_is_invalid() -> None:
    result = compare_records(
        extracted=ExtractedProductionRecord(
            work_date="2026-09-21",
            work_order="WO-001",
            process="PRESS",
            item_code="AB-01",
            actual_quantity=-1,
            defect_quantity=2,
        ),
        expected=_kintone_record(),
    )

    assert result.status == "needs_human_review"
    assert result.differences == ()
    assert result.missing_fields == ("actual_quantity",)
