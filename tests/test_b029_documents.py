from __future__ import annotations

import base64
from pathlib import Path

import pytest

from local_ai_lab.poc_b029.documents import DocumentValidationError, document_to_data_url

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAB"
    "AAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIE"
    "AwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJico"
    "KSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5i"
    "ZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/"
    "8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEE"
    "BSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tb"
    "a3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)


def _two_page_pdf() -> bytes:
    objects = (
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    )
    document = "%PDF-1.4\n"
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document.encode("ascii")))
        document += f"{number} 0 obj\n{body}\nendobj\n"
    startxref = len(document.encode("ascii"))
    document += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    document += "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    document += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n"
    return document.encode("ascii")


def test_document_to_data_url_accepts_png_and_jpeg(tmp_path: Path) -> None:
    png = tmp_path / "report.png"
    jpeg = tmp_path / "report.jpeg"
    png.write_bytes(PNG_BYTES)
    jpeg.write_bytes(JPEG_BYTES)

    assert document_to_data_url(png).startswith("data:image/png;base64,")
    assert document_to_data_url(jpeg).startswith("data:image/jpeg;base64,")


def test_document_to_data_url_rejects_multi_page_pdf(tmp_path: Path) -> None:
    source = tmp_path / "two-pages.pdf"
    source.write_bytes(_two_page_pdf())

    with pytest.raises(DocumentValidationError, match="exactly one page"):
        document_to_data_url(source)


def test_document_to_data_url_rejects_oversized_input(tmp_path: Path) -> None:
    source = tmp_path / "oversized.png"
    source.write_bytes(PNG_BYTES + (b"x" * (5 * 1024 * 1024)))

    with pytest.raises(DocumentValidationError, match="too large"):
        document_to_data_url(source)
