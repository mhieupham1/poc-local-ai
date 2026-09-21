from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


def _load_generator() -> object:
    script_path = Path(__file__).parents[1] / "tools" / "generate_b029_synthetic_documents.py"
    spec = importlib.util.spec_from_file_location("b029_fixture_generator", script_path)
    assert spec is not None
    assert spec.loader is not None
    fixture_generator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixture_generator
    spec.loader.exec_module(fixture_generator)
    return fixture_generator


def test_generator_populates_directory_that_contains_only_its_readme(
    tmp_path: Path, monkeypatch: object
) -> None:
    fixture_generator = _load_generator()

    output = tmp_path / "b029"
    output.mkdir()
    (output / "README.md").write_text("fixture documentation\n", encoding="utf-8")
    monkeypatch.setattr(fixture_generator.shutil, "which", lambda _command: "/usr/bin/rsvg-convert")  # type: ignore[attr-defined]
    monkeypatch.setattr(fixture_generator, "render", lambda *_args: None)  # type: ignore[attr-defined]

    fixture_generator.generate(output)

    assert (output / "cases" / "case-01.json").is_file()
    assert (output / "SHA256SUMS").is_file()


def test_manifest_can_be_rewritten_without_hashing_itself(
    tmp_path: Path, monkeypatch: object
) -> None:
    fixture_generator = _load_generator()
    output = tmp_path / "b029"
    output.mkdir()
    (output / "README.md").write_text("fixture documentation\n", encoding="utf-8")
    monkeypatch.setattr(fixture_generator.shutil, "which", lambda _command: "/usr/bin/rsvg-convert")  # type: ignore[attr-defined]

    def fake_render(_svg: Path, png: Path, pdf: Path) -> None:
        png.write_bytes(b"PNG")
        pdf.write_bytes(b"PDF")

    monkeypatch.setattr(fixture_generator, "render", fake_render)  # type: ignore[attr-defined]
    fixture_generator.generate(output)
    fixture_generator.write_manifest(output)

    for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, relative_file = line.split("  ", maxsplit=1)
        assert expected == hashlib.sha256((output / relative_file).read_bytes()).hexdigest()
