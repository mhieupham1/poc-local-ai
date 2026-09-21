# B-029 Synthetic PoC Implementation Plan

> **For implementer:** use `superpowers:executing-plans` to execute this plan
> task by task.

**Goal:** Implement a command-line B-029 PoC that sends a synthetic production
report image to the existing authenticated Vision API, ranks synthetic rules
through the existing embedding API, compares validated records deterministically
and writes safe human-review reports.

**Architecture:** B-029 is a Python CLI client inside the existing package. It
does not add a service, public route or data store. The CLI validates a local
case, turns a supported image/PDF into an in-memory `data:image` URL, calls the
existing gateway, and writes only sanitized outcome artifacts. A comparator,
rather than an LLM, owns the match decision.

**Tech Stack:** Python 3.12, Pydantic, httpx, Pillow, PyMuPDF, pytest, Ruff,
mypy; existing Qwen3-VL and BGE-M3 OpenAI-compatible gateway APIs.

**Spec:** [B-029 synthetic PoC design](../specs/2026-09-21-b029-synthetic-poc-design.md)

**Global Constraints:**

- Preserve `/v1/chat/completions` and `/v1/embeddings` as the only public AI
  routes. Do not add `/poc` endpoints or change gateway/container behavior.
- Use `gateway.auth.read_token_file`; tokens stay in a mode-`0600` file and
  never enter argv, generated fixture, report or log.
- Fixtures are synthetic only and display `DEMO DATA — NOT PRODUCTION`.
- A malformed Vision response, an unreadable field or an unsupported document
  must result in safe failure or `needs_human_review`, never `match`.
- `result.json`, `result.md` and `evaluation.json` must exclude source bytes,
  data URLs, raw upstream bodies and credentials.
- Unit tests must run without a GPU, Docker daemon or network access.

**Review Focus:**

1. Missing/invalid fields cannot be normalized into a false match.
2. The client rejects unsupported, multi-page or oversized input before upload.
3. Chat/embedding request failures and malformed replies are redacted and do
   not produce a business decision.
4. Ranking changes explanation context only; it cannot change the comparator
   status.
5. Output artifacts are safe to share as a synthetic demo report.

## Task 1: Create business contracts and deterministic comparator

**Files:**

- Create: `src/local_ai_lab/poc_b029/__init__.py`
- Create: `src/local_ai_lab/poc_b029/models.py`
- Create: `src/local_ai_lab/poc_b029/compare.py`
- Create: `tests/test_b029_compare.py`

**Step 1: Write the failing tests.**

Cover an exact match after whitespace/case normalization, a multiple-field
mismatch, and a missing/invalid Vision field. The last case must assert
`needs_human_review` and no differences based on guessed values.

```python
result = compare_records(
    extracted=ExtractedProductionRecord(
        work_date="2026-09-21",
        work_order=" wo-001 ",
        process="press",
        item_code=" ab-01 ",
        actual_quantity=120,
        defect_quantity=2,
    ),
    expected=KintoneProductionRecord(
        work_date=date(2026, 9, 21),
        work_order="WO-001",
        process="PRESS",
        item_code="AB-01",
        actual_quantity=120,
        defect_quantity=2,
    ),
)
assert result.status == "match"
assert result.differences == ()
```

**Step 2: Run the focused test to confirm it fails.**

Run: `uv run pytest -q tests/test_b029_compare.py`

Expected: import/collection failure because the B-029 package does not exist.

**Step 3: Implement the smallest typed contract.**

Define separate Pydantic models so incomplete Vision output cannot be confused
with a source-of-record entry:

```python
class ExtractedProductionRecord(BaseModel):
    work_date: date | None
    work_order: str | None
    process: str | None
    item_code: str | None
    actual_quantity: int | None
    defect_quantity: int | None


class KintoneProductionRecord(BaseModel):
    work_date: date
    work_order: str
    process: str
    item_code: str
    actual_quantity: NonNegativeInt
    defect_quantity: NonNegativeInt
```

Use a `ComparisonStatus` literal with exactly `match`, `mismatch` and
`needs_human_review`. Normalize only non-null values, using ISO dates,
upper-cased collapsed whitespace for identifiers, and integer quantities. If
any extraction field is null, return `needs_human_review` before comparing.

**Step 4: Run the focused test.**

Run: `uv run pytest -q tests/test_b029_compare.py`

Expected: all comparator tests pass.

**Step 5: Commit the contract.**

```bash
git add src/local_ai_lab/poc_b029 tests/test_b029_compare.py
git commit -m "feat: add B-029 comparison contracts"
```

## Task 2: Validate local input and generate reproducible synthetic cases

**Files:**

- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `src/local_ai_lab/poc_b029/documents.py`
- Create: `src/local_ai_lab/poc_b029/fixtures.py`
- Create: `tests/test_b029_documents.py`
- Create: `tests/test_b029_fixtures.py`

**Step 1: Write failing input and fixture tests.**

Test PNG and JPEG acceptance, rejection of a two-page PDF and an input above
the documented five-mebibyte limit. Generate cases in `tmp_path`; assert ten
case JSON files, five expected `match` cases and five expected `mismatch`
cases, and assert each rendered form has the demo-data label.

```python
generated = generate_fixtures(tmp_path / "generated")
assert len(generated) == 10
assert sum(case.expected.status == "match" for case in generated) == 5
assert sum(case.expected.status == "mismatch" for case in generated) == 5
assert "DEMO DATA — NOT PRODUCTION" in generated[0].rendered_text
```

**Step 2: Run the focused tests to confirm they fail.**

Run: `uv run pytest -q tests/test_b029_documents.py tests/test_b029_fixtures.py`

Expected: import/collection failure because the input and fixture modules do
not exist.

**Step 3: Implement input boundaries and fixture generator.**

Add `Pillow` and `PyMuPDF` as runtime dependencies. `documents.py` accepts
only `.png`, `.jpg`, `.jpeg` or `.pdf`; renders only a one-page PDF to PNG in
memory; validates payload size before it is encoded; and returns a MIME-typed
data URL without writing any derived copy. `fixtures.py` creates clearly
labelled forms and paired JSON case manifests with local relative asset paths,
synthetic Kintone records, synthetic rules and expected result.

Ignore `samples/b029/generated/` so a developer cannot accidentally commit
runtime fixture output as a claimed dataset. Tests keep their data under
`tmp_path`.

**Step 4: Run focused tests and formatter.**

Run:

```bash
uv run pytest -q tests/test_b029_documents.py tests/test_b029_fixtures.py
uv run ruff format --check src/local_ai_lab/poc_b029 tests/test_b029_documents.py tests/test_b029_fixtures.py
```

Expected: tests and formatting pass.

**Step 5: Commit the input boundary.**

```bash
git add pyproject.toml uv.lock .gitignore src/local_ai_lab/poc_b029 tests/test_b029_documents.py tests/test_b029_fixtures.py
git commit -m "feat: generate and validate B-029 synthetic inputs"
```

## Task 3: Add a redacted client for the existing Vision and embedding APIs

**Files:**

- Create: `src/local_ai_lab/poc_b029/client.py`
- Create: `src/local_ai_lab/poc_b029/retrieval.py`
- Create: `tests/test_b029_client.py`
- Create: `tests/test_b029_retrieval.py`

**Step 1: Write failing client tests with `httpx.MockTransport`.**

Assert that the Vision request goes only to `/v1/chat/completions`, includes a
Bearer header read from a `0600` credential file, sends `stream: false`, uses
an image data URL and requests JSON-schema output. Assert the embedding request
goes only to `/v1/embeddings`; a wrong vector count, non-numeric vector,
non-2xx response or malformed chat JSON raises a redacted domain error.

```python
response = await client.extract_record(image_data_url=data_url)
assert response.record.work_order == "WO-001"
assert response.request_id
assert "data:image" not in str(response.model_dump())
```

**Step 2: Run the focused tests to confirm they fail.**

Run: `uv run pytest -q tests/test_b029_client.py tests/test_b029_retrieval.py`

Expected: import/collection failure because client and retrieval modules do not
exist.

**Step 3: Implement the gateway client and ranking-only retrieval.**

Use `read_token_file` from `local_ai_lab.gateway.auth`. Generate a UUID for
`X-Request-ID`, set a finite httpx timeout, disable redirects and retain only
safe metadata: request ID, model ID and elapsed time. Parse
`choices[0].message.content` with `json.loads` then validate it as
`ExtractedProductionRecord`; never retain the raw upstream body.

For Vision, send a non-streaming OpenAI chat request with the report image and
`response_format` JSON schema. For embedding, submit the case query plus the
rule texts, validate all returned vectors are finite and same-dimensional, then
calculate cosine similarity in `retrieval.py`. Return at most three ranked
rules. Keep the comparator independent: no ranking value may be passed into
the comparison function.

**Step 4: Run focused tests.**

Run: `uv run pytest -q tests/test_b029_client.py tests/test_b029_retrieval.py`

Expected: all mocked API/error-path tests pass without network access.

**Step 5: Commit the client.**

```bash
git add src/local_ai_lab/poc_b029 tests/test_b029_client.py tests/test_b029_retrieval.py
git commit -m "feat: call existing APIs for B-029 extraction and retrieval"
```

## Task 4: Assemble a safe case runner, reports and CLI commands

**Files:**

- Modify: `src/local_ai_lab/cli.py`
- Create: `src/local_ai_lab/poc_b029/command.py`
- Create: `src/local_ai_lab/poc_b029/report.py`
- Create: `tests/test_b029_command.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing command/report tests.**

Mock the B-029 gateway client, run a generated case and assert that all three
output files are produced. Read the files back and assert they contain status,
differences, model/request IDs and evaluation result but contain neither
`data:image`, image base64, the credential text nor raw chat content.

```python
exit_code = main(
    [
        "poc",
        "b029",
        "run",
        "--case",
        str(case_path),
        "--base-url",
        "https://gateway.example",
        "--credential-file",
        str(token_file),
        "--output",
        str(output_dir),
    ]
)
assert exit_code == 0
assert (output_dir / "result.json").is_file()
assert (output_dir / "result.md").is_file()
assert (output_dir / "evaluation.json").is_file()
```

**Step 2: Run the focused test to confirm it fails.**

Run: `uv run pytest -q tests/test_b029_command.py tests/test_cli.py`

Expected: the parser does not yet recognize `poc b029`.

**Step 3: Implement a narrow CLI contract.**

Register only these commands:

```text
local-ai-lab poc b029 fixtures --output PATH
local-ai-lab poc b029 run --case PATH --base-url URL --credential-file PATH --output PATH
```

`run` loads a case manifest, checks its asset path remains beneath the case
directory, invokes Vision, invokes embedding ranking, invokes the comparator,
then calls an atomic report writer. Any document/client/validation failure
prints a short redacted error to stderr and returns exit code `2`; it writes no
partial result directory. A valid but incomplete extraction must write a
`needs_human_review` report and exit `0`, because this is a valid business
outcome rather than an infrastructure error.

**Step 4: Run focused tests.**

Run: `uv run pytest -q tests/test_b029_command.py tests/test_cli.py`

Expected: parser, case traversal, report-safety and status-path tests pass.

**Step 5: Commit the executable PoC.**

```bash
git add src/local_ai_lab/cli.py src/local_ai_lab/poc_b029 tests/test_b029_command.py tests/test_cli.py
git commit -m "feat: add B-029 PoC command and safe reports"
```

## Task 5: Update operator documentation and verify repository quality gates

**Files:**

- Modify: `README.md`
- Modify: `docs/vast-ai-first-run.md`
- Modify: `docs/b029-poc-overview.md`
- Modify: `docs/b029-data-request.md`

**Step 1: Add only operator-facing decisions and command entry points.**

Link the README and Vast guide to the B-029 overview. Add the two implemented
commands and explain that `fixtures` is synthetic, while real input is allowed
only after the data-request conditions are satisfied. Keep API behavior,
runtime ports and mutable image/template details owned by their existing files.

**Step 2: Run all local quality gates.**

Run:

```bash
uv sync --dev
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
docker buildx build --check --platform linux/amd64 --file deploy/vast/Dockerfile .
git diff --check
```

Expected: all commands return exit code `0`.

**Step 3: Commit documentation and verification work.**

```bash
git add README.md docs/vast-ai-first-run.md docs/b029-poc-overview.md docs/b029-data-request.md
git commit -m "docs: document B-029 synthetic PoC operation"
```

## Task 6: Rebuild the Vast image and perform the controlled integration run

**Files:**

- Create locally outside Git: `reports/b029/`
- Create on the temporary Vast volume: `/workspace/b029-fixtures/` and
  `/workspace/reports/b029/`

**Step 1: Build and publish a new immutable image tag.**

Follow the existing [Vast first-run guide](../../vast-ai-first-run.md) to build
and push a new Linux/amd64 tag, record its image digest, update the private
Vast template and wait for `local-ai-embedding`, `local-ai-llm` and
`local-ai-gateway` to be ready. Do not modify an image tag that has already
been benchmarked.

**Step 2: Generate only synthetic fixtures on the instance.**

Run inside the instance:

```bash
cd /opt/local-ai
.venv/bin/local-ai-lab poc b029 fixtures --output /workspace/b029-fixtures
```

Expected: ten labelled cases are generated; no internal data is present.

**Step 3: Run one known match and one known mismatch through the gateway.**

Run inside the instance:

```bash
.venv/bin/local-ai-lab poc b029 run \
  --case /workspace/b029-fixtures/case-01.json \
  --base-url http://127.0.0.1:18000 \
  --credential-file /run/local-ai/gateway-token \
  --output /workspace/reports/b029/case-01

.venv/bin/local-ai-lab poc b029 run \
  --case /workspace/b029-fixtures/case-06.json \
  --base-url http://127.0.0.1:18000 \
  --credential-file /run/local-ai/gateway-token \
  --output /workspace/reports/b029/case-06
```

Expected: both calls contain different Vision and embedding request IDs; the
first evaluation passes as `match`, the second passes as `mismatch`, and no
report contains token or image content.

**Step 4: Inspect, collect and destroy.**

Inspect only the sanitized report artifacts, copy them through the approved
channel, record elapsed time and gateway/model versions, then destroy the Vast
instance when the approved experiment window ends. Do not retain the synthetic
input directory or runtime token as a deliverable.
