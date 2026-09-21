from __future__ import annotations

import math
from dataclasses import dataclass


class RetrievalError(ValueError):
    """Raised when embedding output cannot safely rank the supplied rules."""


@dataclass(frozen=True)
class RankedRule:
    text: str
    score: float


def rank_rules(
    *,
    rules: tuple[str, ...],
    vectors: tuple[tuple[object, ...], ...],
    limit: int = 3,
) -> tuple[RankedRule, ...]:
    if not rules or limit < 1:
        raise RetrievalError("rules and limit must be positive")
    if len(vectors) != len(rules) + 1:
        raise RetrievalError("embedding vector count does not match rules")
    normalized_vectors = tuple(_validated_vector(vector) for vector in vectors)
    dimensions = {len(vector) for vector in normalized_vectors}
    if len(dimensions) != 1:
        raise RetrievalError("embedding vectors have inconsistent dimensions")
    query = normalized_vectors[0]
    ranked = tuple(
        RankedRule(text=rule, score=_cosine(query, vector))
        for rule, vector in zip(rules, normalized_vectors[1:], strict=True)
    )
    return tuple(sorted(ranked, key=lambda item: item.score, reverse=True)[:limit])


def _validated_vector(vector: tuple[object, ...]) -> tuple[float, ...]:
    if not vector:
        raise RetrievalError("embedding vector is empty")
    values: list[float] = []
    for component in vector:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise RetrievalError("embedding vector is non-numeric")
        value = float(component)
        if not math.isfinite(value):
            raise RetrievalError("embedding vector is non-finite")
        values.append(value)
    return tuple(values)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise RetrievalError("embedding vector has zero magnitude")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
