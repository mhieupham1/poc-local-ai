from __future__ import annotations

import json
from pathlib import Path

from local_ai_lab.poc_b029.fixtures import generate_fixtures


def test_generate_fixtures_creates_balanced_labelled_cases(tmp_path: Path) -> None:
    generated = generate_fixtures(tmp_path / "generated")

    assert len(generated) == 10
    assert sum(case.expected.status == "match" for case in generated) == 5
    assert sum(case.expected.status == "mismatch" for case in generated) == 5
    assert "DEMO DATA — NOT PRODUCTION" in generated[0].rendered_text

    documents = [json.loads(case.path.read_text(encoding="utf-8")) for case in generated]
    assert all(document["data_classification"] == "synthetic" for document in documents)
    assert all(
        (case.path.parent / document["report_path"]).is_file()
        for case, document in zip(generated, documents, strict=True)
    )
