"""
PDF → image conversion for preview and OCR (OpenCV cannot read PDFs directly).
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from app.core.config_loader import get_config


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def _pdf_dpi() -> int:
    return int(get_config()["ocr"].get("pdf_render_dpi", 200))


def rasterize_pdf_first_page(pdf_path: Path, output_path: Path) -> Path:
    """Render first page of PDF to PNG using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for PDF uploads. Install: pip install pymupdf"
        ) from exc

    dpi = _pdf_dpi()
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        pix = doc.load_page(0).get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(output_path))

    return output_path


@contextmanager
def document_image_source(file_path: str | Path) -> Generator[Path, None, None]:
    """
    Yield a path OpenCV/Tesseract can read.
    Creates a temporary PNG for PDF inputs and deletes it after use.
    """
    source = Path(file_path)
    if not is_pdf(source):
        yield source
        return

    temp_dir = source.parent
    temp_png = temp_dir / f"_pdf_raster_{uuid.uuid4().hex}.png"
    try:
        rasterize_pdf_first_page(source, temp_png)
        yield temp_png
    finally:
        if temp_png.exists():
            temp_png.unlink()


class PreparedUpload:
    """Paths and URLs after storing an upload for validation."""

    def __init__(
        self,
        ocr_path: Path,
        preview_url: str,
        *,
        original_url: str | None = None,
        temp_paths: list[Path] | None = None,
    ) -> None:
        self.ocr_path = ocr_path
        self.preview_url = preview_url
        self.original_url = original_url
        self._temp_paths = temp_paths or []

    def cleanup(self) -> None:
        for path in self._temp_paths:
            if path.exists():
                path.unlink()


def prepare_upload(
    source_path: Path,
    upload_dir: Path,
    filename: str | None,
    content_type: str | None,
) -> PreparedUpload:
    """
    Copy upload to static/uploads and ensure a PNG preview exists for the dashboard.
    """
    upload_dir.mkdir(parents=True, exist_ok=True)

    if is_pdf(source_path) or content_type == "application/pdf":
        preview_name = f"{uuid.uuid4().hex}_preview.png"
        preview_path = upload_dir / preview_name
        rasterize_pdf_first_page(source_path, preview_path)

        pdf_name = f"{uuid.uuid4().hex}.pdf"
        pdf_dest = upload_dir / pdf_name
        shutil.copy2(source_path, pdf_dest)

        return PreparedUpload(
            ocr_path=preview_path,
            preview_url=f"/static/uploads/{preview_name}",
            original_url=f"/static/uploads/{pdf_name}",
        )

    stored_name = f"{uuid.uuid4().hex}{source_path.suffix.lower() or '.jpg'}"
    dest = upload_dir / stored_name
    shutil.copy2(source_path, dest)
    url = f"/static/uploads/{stored_name}"
    return PreparedUpload(ocr_path=dest, preview_url=url)
