from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, UnidentifiedImageError

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class DocumentValidationError(ValueError):
    """Raised when a local document is unsafe or unsupported for B-029."""


def document_to_data_url(source: Path) -> str:
    """Load one supported local document without persisting derived content."""
    if not source.is_file():
        raise DocumentValidationError("document path is not a regular file")
    suffix = source.suffix.lower()
    if suffix not in {*_IMAGE_MIME_TYPES, ".pdf"}:
        raise DocumentValidationError("document must be PNG, JPEG, or PDF")
    raw = source.read_bytes()
    _ensure_size(raw)
    if suffix == ".pdf":
        payload = _render_single_page_pdf(raw)
        mime_type = "image/png"
    else:
        _verify_image(raw)
        payload = raw
        mime_type = _IMAGE_MIME_TYPES[suffix]
    _ensure_size(payload)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _ensure_size(payload: bytes) -> None:
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("document is too large; maximum is 5 MiB")


def _verify_image(payload: bytes) -> None:
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise DocumentValidationError("image cannot be decoded") from exc


def _render_single_page_pdf(payload: bytes) -> bytes:
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")  # type: ignore[no-untyped-call]
    except (RuntimeError, ValueError) as exc:
        raise DocumentValidationError("PDF cannot be decoded") from exc
    try:
        if document.page_count != 1:
            raise DocumentValidationError("PDF must contain exactly one page")
        pixmap = document[0].get_pixmap(
            matrix=pymupdf.Matrix(2, 2),  # type: ignore[no-untyped-call]
            alpha=False,
        )
        rendered: object = pixmap.tobytes("png")  # type: ignore[no-untyped-call]
        if not isinstance(rendered, bytes):
            raise DocumentValidationError("PDF rendering returned an invalid image")
        return rendered
    finally:
        document.close()  # type: ignore[no-untyped-call]
