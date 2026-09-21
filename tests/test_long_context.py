from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_ai_lab.bench.command import load_workload
from local_ai_lab.bench.long_context import build_long_context_cases, write_workload


class WordTokenizer:
    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


def test_builds_positioned_cases_within_reserved_context_budget() -> None:
    tokenizer = WordTokenizer()
    source = " ".join(f"word-{index}" for index in range(500))

    cases = build_long_context_cases(
        source=source,
        source_id="book-en",
        tokenizer=tokenizer,
        context_windows=(128,),
        positions=("start", "middle", "end"),
        reserve_tokens=16,
        model="local-vision-language",
    )

    assert [case["id"] for case in cases] == [
        "long-128-start",
        "long-128-middle",
        "long-128-end",
    ]
    for case in cases:
        content = case["payload"]["messages"][0]["content"]
        assert len(tokenizer.encode(content)) <= 112
        assert case["expected_contains"] in content
        assert case["metadata"]["source_id"] == "book-en"
        assert case["metadata"]["prompt_tokens"] == len(tokenizer.encode(content))

    ratios = []
    for case in cases:
        content = case["payload"]["messages"][0]["content"]
        marker = case["expected_contains"]
        ratios.append(len(tokenizer.encode(content.split(marker, 1)[0])) / 112)
    assert ratios[0] < 0.25
    assert 0.35 < ratios[1] < 0.65
    assert ratios[2] > 0.75


def test_rejects_source_that_cannot_fill_requested_context() -> None:
    with pytest.raises(ValueError, match="source is too short"):
        build_long_context_cases(
            source="only a few words",
            source_id="short",
            tokenizer=WordTokenizer(),
            context_windows=(128,),
            positions=("middle",),
            reserve_tokens=16,
            model="local-vision-language",
        )


def test_write_workload_creates_jsonl_without_source_document(tmp_path: Path) -> None:
    cases = build_long_context_cases(
        source=" ".join(f"word-{index}" for index in range(500)),
        source_id="book-en",
        tokenizer=WordTokenizer(),
        context_windows=(128,),
        positions=("middle",),
        reserve_tokens=16,
        model="local-vision-language",
    )

    output = tmp_path / "generated" / "long.jsonl"
    write_workload(cases, output)

    document = json.loads(output.read_text().strip())
    assert document["id"] == "long-128-middle"
    assert "word-499" not in output.read_text()


def test_load_workload_preserves_case_id_and_expected_marker(tmp_path: Path) -> None:
    workload = tmp_path / "long.jsonl"
    workload.write_text(
        json.dumps(
            {
                "id": "long-128-middle",
                "expected_contains": "LC-128-MIDDLE-7392",
                "payload": {"model": "local-vision-language", "messages": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases, _ = load_workload(workload)

    assert cases[0].case_id == "long-128-middle"
    assert cases[0].expected_contains == "LC-128-MIDDLE-7392"
    assert cases[0].payload["model"] == "local-vision-language"
