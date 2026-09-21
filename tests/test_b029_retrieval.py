from __future__ import annotations

import pytest

from local_ai_lab.poc_b029.retrieval import RetrievalError, rank_rules


def test_rank_rules_orders_by_cosine_similarity_and_limits_to_three() -> None:
    ranked = rank_rules(
        rules=("date", "work order", "quantity", "defect"),
        vectors=((1.0, 0.0), (0.9, 0.1), (0.0, 1.0), (-1.0, 0.0), (0.5, 0.5)),
    )

    assert [item.text for item in ranked] == ["date", "defect", "work order"]
    assert ranked[0].score == pytest.approx(0.9938837347)


@pytest.mark.parametrize(
    "vectors",
    [
        ((1.0, 0.0),),
        ((1.0, 0.0), (0.0, "not-a-number")),
        ((1.0, 0.0), (0.0, 1.0), (1.0,)),
    ],
)
def test_rank_rules_rejects_invalid_embedding_vectors(
    vectors: tuple[tuple[object, ...], ...],
) -> None:
    with pytest.raises(RetrievalError, match="embedding"):
        rank_rules(rules=("rule"), vectors=vectors)
