from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from local_ai_lab.config import (
    config_fingerprint,
    load_settings_from_env_file,
    validate_env_template,
)
from local_ai_lab.stack import validate_compose


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-ai-lab",
        description="Portable control plane for local AI inference experiments.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    env_parser = commands.add_parser("env", help="Validate lab environment configuration.")
    env_commands = env_parser.add_subparsers(dest="env_command", required=True)
    validate_parser = env_commands.add_parser("validate", help="Validate an env template.")
    validate_parser.add_argument("--env-file", required=True, type=Path)

    stack_parser = commands.add_parser("stack", help="Validate the GPU service stack.")
    stack_commands = stack_parser.add_subparsers(dest="stack_command", required=True)
    stack_validate = stack_commands.add_parser("validate", help="Check compose exposure rules.")
    stack_validate.add_argument("--compose-file", type=Path, default=Path("compose.yaml"))
    stack_validate.add_argument("--env-file", type=Path)

    bench_parser = commands.add_parser("bench", help="Benchmark inference through the gateway.")
    bench_commands = bench_parser.add_subparsers(dest="bench_command", required=True)
    bench_chat = bench_commands.add_parser(
        "chat", help="Measure streaming text or vision requests."
    )
    bench_chat.add_argument("--workload", required=True, type=Path)
    bench_chat.add_argument("--output", required=True, type=Path)
    bench_chat.add_argument("--credential-file", required=True, type=Path)
    bench_chat.add_argument("--base-url", default="http://127.0.0.1:8443")
    bench_chat.add_argument("--concurrency", default="1")
    bench_chat.add_argument("--requests-per-level", type=int, default=10)
    bench_chat.add_argument("--timeout", type=float, default=120.0)
    bench_embedding = bench_commands.add_parser(
        "embedding", help="Measure embedding latency and throughput."
    )
    bench_embedding.add_argument("--workload", required=True, type=Path)
    bench_embedding.add_argument("--output", required=True, type=Path)
    bench_embedding.add_argument("--credential-file", required=True, type=Path)
    bench_embedding.add_argument("--base-url", default="http://127.0.0.1:8443")
    bench_embedding.add_argument("--concurrency", default="1")
    bench_embedding.add_argument("--requests-per-level", type=int, default=10)
    bench_embedding.add_argument("--timeout", type=float, default=120.0)

    workload_parser = commands.add_parser("workload", help="Generate benchmark workloads.")
    workload_commands = workload_parser.add_subparsers(dest="workload_command", required=True)
    long_context = workload_commands.add_parser(
        "long-context", help="Generate deterministic long-context recall cases."
    )
    long_context.add_argument("--source", required=True, type=Path)
    long_context.add_argument("--source-id", required=True)
    long_context.add_argument("--output", required=True, type=Path)
    long_context.add_argument("--context-windows", default="32768,65536")
    long_context.add_argument("--positions", default="start,middle,end")
    long_context.add_argument("--reserve-tokens", type=int, default=1024)
    long_context.add_argument("--model", default="local-vision-language")
    long_context.add_argument("--tokenizer", default="Qwen/Qwen3-VL-8B-Instruct")
    long_context.add_argument(
        "--tokenizer-revision",
        default="0c351dd01ed87e9c1b53cbc748cba10e6187ff3b",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    if args.command == "env" and args.env_command == "validate":
        env_file: Path = args.env_file
        if not env_file.is_file():
            print(f"env file does not exist: {env_file}", file=sys.stderr)
            return 2
        if env_file.name.endswith(".example"):
            result = validate_env_template(env_file)
            stream = sys.stdout if result.valid else sys.stderr
            print(json.dumps(result.model_dump(mode="json"), sort_keys=True), file=stream)
            return 0 if result.valid else 2

        try:
            settings = load_settings_from_env_file(env_file)
        except (ValidationError, ValueError) as exc:
            print(f"runtime env invalid: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "config_fingerprint": config_fingerprint(settings),
                    "path": str(env_file),
                    "valid": True,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "stack" and args.stack_command == "validate":
        stack_result = validate_compose(args.compose_file, env_file=args.env_file)
        stream = sys.stdout if stack_result.valid else sys.stderr
        print(json.dumps(stack_result.model_dump(mode="json"), sort_keys=True), file=stream)
        return 0 if stack_result.valid else 2

    if args.command == "bench" and args.bench_command in {"chat", "embedding"}:
        from local_ai_lab.bench.command import (
            parse_concurrency,
            run_chat_command_sync,
            run_embedding_command_sync,
        )

        try:
            if args.requests_per_level <= 0:
                raise ValueError("requests-per-level must be positive")
            command = (
                run_chat_command_sync
                if args.bench_command == "chat"
                else run_embedding_command_sync
            )
            paths = command(
                workload=args.workload,
                output=args.output,
                credential_file=args.credential_file,
                base_url=args.base_url,
                concurrency_levels=parse_concurrency(args.concurrency),
                requests_per_level=args.requests_per_level,
                timeout_seconds=args.timeout,
            )
        except (OSError, ValueError) as exc:
            print(f"benchmark configuration invalid: {exc}", file=sys.stderr)
            return 2
        print(
            json.dumps(
                {
                    "raw_jsonl": str(paths.raw_jsonl),
                    "summary_json": str(paths.summary_json),
                    "summary_markdown": str(paths.summary_markdown),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "workload" and args.workload_command == "long-context":
        from local_ai_lab.bench.long_context import (
            build_long_context_cases,
            load_pretrained_tokenizer,
            write_workload,
        )

        try:
            if not args.source.is_file():
                raise ValueError(f"source file does not exist: {args.source}")
            context_windows = tuple(
                int(value.strip()) for value in args.context_windows.split(",") if value.strip()
            )
            positions = tuple(value.strip() for value in args.positions.split(",") if value.strip())
            tokenizer = load_pretrained_tokenizer(args.tokenizer, args.tokenizer_revision)
            cases = build_long_context_cases(
                source=args.source.read_text(encoding="utf-8"),
                source_id=args.source_id,
                tokenizer=tokenizer,
                context_windows=context_windows,
                positions=positions,
                reserve_tokens=args.reserve_tokens,
                model=args.model,
            )
            write_workload(cases, args.output)
        except (OSError, ValueError) as exc:
            print(f"long-context workload invalid: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"cases": len(cases), "output": str(args.output)}, sort_keys=True))
        return 0

    parser.error("unsupported command")
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
