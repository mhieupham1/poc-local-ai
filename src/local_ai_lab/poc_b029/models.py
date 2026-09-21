from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, NonNegativeInt

FieldName = Literal[
    "work_date",
    "work_order",
    "process",
    "item_code",
    "actual_quantity",
    "defect_quantity",
]
ComparisonStatus = Literal["match", "mismatch", "needs_human_review"]

FIELD_ORDER: tuple[FieldName, ...] = (
    "work_date",
    "work_order",
    "process",
    "item_code",
    "actual_quantity",
    "defect_quantity",
)


class ExtractedProductionRecord(BaseModel):
    """Vision output; null means the field could not be read safely."""

    model_config = ConfigDict(extra="forbid")

    work_date: date | None
    work_order: str | None
    process: str | None
    item_code: str | None
    actual_quantity: int | None
    defect_quantity: int | None


class KintoneProductionRecord(BaseModel):
    """Source-of-record fixture supplied by the simulated Kintone export."""

    model_config = ConfigDict(extra="forbid")

    work_date: date
    work_order: str
    process: str
    item_code: str
    actual_quantity: NonNegativeInt
    defect_quantity: NonNegativeInt


class FieldDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    report_value: str | int
    kintone_value: str | int
    reason: str


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ComparisonStatus
    differences: tuple[FieldDifference, ...]
    missing_fields: tuple[FieldName, ...]
