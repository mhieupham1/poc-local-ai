from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol


class TokenizerLike(Protocol):
    def encode(self, text: str) -> Sequence[Any]: ...

    def decode(self, tokens: list[Any]) -> str: ...


class _PretrainedTokenizerAdapter:
    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    def encode(self, text: str) -> list[int]:
        return list(self._tokenizer.encode(text).ids)

    def decode(self, tokens: list[Any]) -> str:
        return str(self._tokenizer.decode(tokens, skip_special_tokens=False))


_POSITION_RATIOS = {"start": 0.0, "middle": 0.5, "end": 1.0}


def load_pretrained_tokenizer(identifier: str, revision: str) -> TokenizerLike:
    try:
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_pretrained(identifier, revision=revision)
    except Exception as exc:
        raise ValueError(f"could not load tokenizer {identifier} at revision {revision}") from exc
    return _PretrainedTokenizerAdapter(tokenizer)


def build_long_context_cases(
    *,
    source: str,
    source_id: str,
    tokenizer: TokenizerLike,
    context_windows: tuple[int, ...],
    positions: tuple[str, ...],
    reserve_tokens: int,
    model: str,
) -> list[dict[str, Any]]:
    if not source.strip():
        raise ValueError("source must not be empty")
    if not source_id.strip() or not model.strip():
        raise ValueError("source_id and model must not be empty")
    if reserve_tokens <= 0:
        raise ValueError("reserve_tokens must be positive")
    if not context_windows or any(window <= reserve_tokens for window in context_windows):
        raise ValueError("context windows must be greater than reserve_tokens")
    unknown_positions = set(positions) - set(_POSITION_RATIOS)
    if not positions or unknown_positions:
        raise ValueError("positions must contain start, middle, or end")

    source_tokens = list(tokenizer.encode(source))
    cases: list[dict[str, Any]] = []
    for context_window in context_windows:
        prompt_budget = context_window - reserve_tokens
        for position in positions:
            marker = f"LC-{context_window}-{position.upper()}-7392"
            prefix = "TÀI LIỆU:\n"
            marker_block = f"\n[DỮ KIỆN KIỂM THỬ] Mã xác minh là {marker}.\n"
            suffix = "\nCÂU HỎI: Mã xác minh trong tài liệu là gì? Chỉ trả lời chính xác mã."
            overhead = len(tokenizer.encode(prefix + marker_block + suffix))
            source_budget = prompt_budget - overhead
            if source_budget <= 0:
                raise ValueError("context window is too small for benchmark instructions")
            if len(source_tokens) < source_budget:
                raise ValueError(
                    f"source is too short for context window {context_window}: "
                    f"need at least {source_budget} tokens, got {len(source_tokens)}"
                )

            selected = source_tokens[:source_budget]
            content = _render(
                tokenizer=tokenizer,
                selected=selected,
                position=position,
                prefix=prefix,
                marker_block=marker_block,
                suffix=suffix,
            )
            while len(tokenizer.encode(content)) > prompt_budget and selected:
                selected.pop()
                content = _render(
                    tokenizer=tokenizer,
                    selected=selected,
                    position=position,
                    prefix=prefix,
                    marker_block=marker_block,
                    suffix=suffix,
                )
            prompt_tokens = len(tokenizer.encode(content))
            cases.append(
                {
                    "id": f"long-{context_window}-{position}",
                    "expected_contains": marker,
                    "metadata": {
                        "context_window": context_window,
                        "needle_position": position,
                        "prompt_tokens": prompt_tokens,
                        "reserve_tokens": reserve_tokens,
                        "source_id": source_id,
                    },
                    "payload": {
                        "model": model,
                        "messages": [{"role": "user", "content": content}],
                        "temperature": 0,
                        "max_tokens": min(reserve_tokens, 64),
                    },
                }
            )
    return cases


def _render(
    *,
    tokenizer: TokenizerLike,
    selected: list[Any],
    position: str,
    prefix: str,
    marker_block: str,
    suffix: str,
) -> str:
    split_at = round(len(selected) * _POSITION_RATIOS[position])
    before = tokenizer.decode(selected[:split_at])
    after = tokenizer.decode(selected[split_at:])
    return prefix + before + marker_block + after + suffix


def write_workload(cases: list[dict[str, Any]], output: Path) -> None:
    if not cases:
        raise ValueError("workload must contain at least one case")
    output.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
    output.write_text(content, encoding="utf-8")
