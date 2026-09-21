from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from local_ai_lab.cli import build_parser, main


def test_help_lists_implemented_commands(capsys: object) -> None:
    assert main(["--help"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert "env" in output
    assert "stack" in output
    assert "bench" in output
    assert "rag" not in output


def test_env_validate_accepts_example_template(capsys: object) -> None:
    assert main(["env", "validate", "--env-file", ".env.example"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]

    assert "valid" in output
    assert str(Path(".env.example")) in output


def test_env_validate_returns_nonzero_for_missing_template(capsys: object) -> None:
    assert main(["env", "validate", "--env-file", "missing.env"]) == 2
    error = capsys.readouterr().err  # type: ignore[attr-defined]

    assert "does not exist" in error


def test_module_entrypoint_executes_command() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_ai_lab.cli",
            "env",
            "validate",
            "--env-file",
            ".env.example",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert '"valid": true' in completed.stdout


def test_stack_validate_command_reports_safe_compose(capsys: object) -> None:
    assert main(["stack", "validate", "--compose-file", "compose.yaml"]) == 0

    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output["valid"] is True
    assert "llm" not in output["published_ports"]


def test_bench_command_is_registered() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "bench",
            "chat",
            "--workload",
            "benchmarks/workloads/text.jsonl",
            "--output",
            "reports/test",
            "--credential-file",
            "secrets/runtime-token",
        ]
    )

    assert args.command == "bench"
    assert args.bench_command == "chat"
    assert args.concurrency == "1"

    embedding_args = parser.parse_args(
        [
            "bench",
            "embedding",
            "--workload",
            "benchmarks/workloads/embedding.jsonl",
            "--output",
            "reports/embedding",
            "--credential-file",
            "secrets/runtime-token",
        ]
    )
    assert embedding_args.bench_command == "embedding"


def test_runtime_env_rejects_missing_credential_file(tmp_path: Path, capsys: object) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AI_LLM_BASE_URL=http://127.0.0.1:8000",
                "AI_EMBEDDING_BASE_URL=http://127.0.0.1:8001",
                f"AI_CREDENTIAL_FILE={tmp_path / 'missing-credential'}",
                "AI_LLM_MODEL=Qwen/Qwen3-VL-8B-Instruct",
                "AI_EMBEDDING_MODEL=BAAI/bge-m3",
                "AI_REQUEST_TIMEOUT_SECONDS=120",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["env", "validate", "--env-file", str(env_file)]) == 2
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "credential file does not exist" in error


def test_workload_command_generates_long_context_jsonl(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    from local_ai_lab.bench import long_context

    class WordTokenizer:
        def encode(self, text: str) -> list[str]:
            return text.split()

        def decode(self, tokens: list[str]) -> str:
            return " ".join(tokens)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        long_context,
        "load_pretrained_tokenizer",
        lambda _identifier, _revision: WordTokenizer(),
    )
    source = tmp_path / "source.txt"
    source.write_text(" ".join(f"word-{index}" for index in range(500)), encoding="utf-8")
    output = tmp_path / "generated" / "long.jsonl"

    exit_code = main(
        [
            "workload",
            "long-context",
            "--source",
            str(source),
            "--source-id",
            "book-en",
            "--output",
            str(output),
            "--context-windows",
            "128",
            "--positions",
            "start,middle,end",
            "--reserve-tokens",
            "16",
        ]
    )

    assert exit_code == 0
    assert len(output.read_text().splitlines()) == 3
    result = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert result["cases"] == 3
    assert result["output"] == str(output)
