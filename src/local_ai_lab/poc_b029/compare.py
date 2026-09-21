from __future__ import annotations

from datetime import date

from local_ai_lab.poc_b029.models import (
    FIELD_ORDER,
    ComparisonResult,
    ExtractedProductionRecord,
    FieldDifference,
    FieldName,
    KintoneProductionRecord,
)


def compare_records(
    *,
    extracted: ExtractedProductionRecord,
    expected: KintoneProductionRecord,
) -> ComparisonResult:
    """Compare only complete Vision output; incomplete output is never a match."""
    review_fields = tuple(
        field for field in FIELD_ORDER if not _is_usable(field, getattr(extracted, field))
    )
    if review_fields:
        return ComparisonResult(
            status="needs_human_review",
            differences=(),
            missing_fields=review_fields,
        )

    differences = tuple(
        difference
        for field in FIELD_ORDER
        if (difference := _difference(field, extracted, expected)) is not None
    )
    return ComparisonResult(
        status="mismatch" if differences else "match",
        differences=differences,
        missing_fields=(),
    )


def _difference(
    field: FieldName,
    extracted: ExtractedProductionRecord,
    expected: KintoneProductionRecord,
) -> FieldDifference | None:
    report_value = getattr(extracted, field)
    kintone_value = getattr(expected, field)
    normalized_report = _normalize(field, report_value)
    normalized_kintone = _normalize(field, kintone_value)
    if normalized_report == normalized_kintone:
        return None
    return FieldDifference(
        field=field,
        report_value=normalized_report,
        kintone_value=normalized_kintone,
        reason="normalized values differ",
    )


def _normalize(field: FieldName, value: date | str | int | None) -> str | int:
    if value is None:
        raise ValueError("cannot normalize a missing value")
    if field in {"actual_quantity", "defect_quantity"}:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
        return value
    if field == "work_date":
        if not isinstance(value, date):
            raise ValueError("work_date must be an ISO date")
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = " ".join(value.split()).upper()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


def _is_usable(field: FieldName, value: date | str | int | None) -> bool:
    try:
        _normalize(field, value)
    except ValueError:
        return False
    return True
