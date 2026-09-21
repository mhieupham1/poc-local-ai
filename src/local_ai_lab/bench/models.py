from __future__ import annotations

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, PositiveInt


class RequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    concurrency: PositiveInt
    success: bool
    status_code: int | None
    prompt_tokens: NonNegativeInt | None
    output_tokens: NonNegativeInt | None
    output_items: NonNegativeInt | None = None
    ttft_seconds: NonNegativeFloat | None
    e2e_seconds: NonNegativeFloat
    tpot_seconds: NonNegativeFloat | None
    decoding_tokens_per_second: NonNegativeFloat | None
    request_output_tokens_per_second: NonNegativeFloat | None
    error: str | None
    case_id: str | None = None
    evaluation_passed: bool | None = None
