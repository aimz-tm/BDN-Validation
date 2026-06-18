"""
OCR engine — Phase 1 (improved).
Tesseract wrapper with per-doc-type PSM mode, high-DPI PDF rendering,
no arbitrary resize cap, and multi-pass retry on low confidence.

Changes from original:
  - PSM 6 for DIGITAL (uniform block), PSM 4 for HANDWRITTEN (single column)
  - PDF render DPI raised to 300 (was 200)
  - Removed _resize_for_ocr() cap — large scans are processed at full resolution
  - Upscale is done in preprocessor.py if the image is too small, not here
  - Multi-pass: if first pass confidence < 0.75, retry with alternate PSM and keep best
  - Processing mode tag added to all return paths for upstream diagnostics
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

try:
    import pytesseract  # type: ignore
    import os
    from dotenv import load_dotenv
    load_dotenv("config/.env")
    _tesseract_path = os.getenv("TESSERACT_PATH")
    if _tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = _tesseract_path
    _tesseract_available = True
except ImportError:
    _tesseract_available = False

try:
    import cv2  # type: ignore
    import numpy as np
    _cv2_available = True
except ImportError:
    _cv2_available = False

try:
    import pdfplumber  # type: ignore
    _pdfplumber_available = True
except ImportError:
    _pdfplumber_available = False

try:
    from PIL import Image  # type: ignore
    _pil_available = True
except ImportError:
    _pil_available = False

from core.config_loader import get_config


# PSM modes per document type:
#   PSM 6: assume a uniform block of text — best for structured printed forms
#   PSM 4: assume a single column of variable-size text — better for handwritten
#   PSM 3: fully automatic (default) — fallback when type unknown
_PSM_BY_DOCTYPE = {
    "DIGITAL": 6,
    "HANDWRITTEN": 4,
    None: 3,
}


def _tesseract_from_array(img_array: Any, psm: int = 6) -> dict[str, Any]:
    """Run Tesseract using image_to_data — gives both text and confidence."""
    if not _tesseract_available:
        return {"text": "", "word_confidences": [], "mean_confidence": 0.0, "raw_data": {}}

    config_str = f"--oem 3 --psm {psm}"
    try:
        data = pytesseract.image_to_data(
            img_array,
            output_type=pytesseract.Output.DICT,
            config=config_str,
        )
        # Reconstruct text preserving line structure
        lines: list[str] = []
        prev_line = None
        cur_words: list[str] = []
        for i, word in enumerate(data["text"]):
            word = str(word).strip()
            line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            if line_key != prev_line:
                if cur_words:
                    lines.append(" ".join(cur_words))
                cur_words = []
                prev_line = line_key
            if word:
                cur_words.append(word)
        if cur_words:
            lines.append(" ".join(cur_words))
        text = "\n".join(lines)

        confidences = [int(c) for c in data["conf"] if str(c).strip() not in ("-1", "")]
        mean_conf = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
    except Exception:
        # Fallback to image_to_string
        try:
            text = pytesseract.image_to_string(img_array, config=f"--oem 3 --psm {psm}")
        except Exception:
            text = ""
        confidences = []
        mean_conf = 0.0
        data = {}

    return {
        "text": text,
        "word_confidences": confidences,
        "mean_confidence": round(mean_conf, 3),
        "raw_data": data,
    }


def _run_with_retry(img_array: Any, doc_type: str | None) -> dict[str, Any]:
    """
    Run Tesseract with the doc-type-appropriate PSM.
    If confidence is below 0.75, retry with alternate PSM and keep the best result.
    """
    primary_psm = _PSM_BY_DOCTYPE.get(doc_type, 3)
    result = _tesseract_from_array(img_array, psm=primary_psm)

    # Multi-pass retry on low confidence
    if result["mean_confidence"] < 0.75:
        # Try PSM 3 (auto) as a fallback
        alt_psm = 3 if primary_psm != 3 else 6
        alt_result = _tesseract_from_array(img_array, psm=alt_psm)
        if alt_result["mean_confidence"] > result["mean_confidence"]:
            result = alt_result
            result["psm_used"] = alt_psm
            result["retry_triggered"] = True
            return result

    result["psm_used"] = primary_psm
    result["retry_triggered"] = False
    return result


def _extract_from_image_file(file_path: Path, doc_type: str | None = None) -> dict[str, Any]:
    if _cv2_available:
        img = cv2.imread(str(file_path))
        if img is not None:
            if doc_type:
                from services.ocr_service.preprocessor import preprocess_for_doctype
                img = preprocess_for_doctype(img, doc_type)
            result = _run_with_retry(img, doc_type)
            result["processing_mode"] = "tesseract_image"
            return result
    if _pil_available:
        img = Image.open(file_path)
        result = _run_with_retry(img, doc_type)
        result["processing_mode"] = "tesseract_pil"
        return result
    return {"text": "", "word_confidences": [], "mean_confidence": 0.0, "raw_data": {}, "processing_mode": "unavailable"}


def _extract_from_pdf(file_path: Path, doc_type: str | None = None) -> dict[str, Any]:
    """Try pdfplumber text layer first; fall back to Tesseract on rendered pages."""
    cfg = get_config().get("ocr", {})
    dpi = int(cfg.get("pdf_render_dpi", 300))  # default raised to 300 for better OCR

    # Try text layer (only for first/classification pass, skip on doc_type second pass)
    if _pdfplumber_available and not doc_type:
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                # Extract from ALL pages and concatenate
                page_texts = []
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    if t.strip():
                        page_texts.append(t)
                combined = "\n\n".join(page_texts)
                if len(combined.strip()) > 50:
                    return {
                        "text": combined,
                        "word_confidences": [],
                        "mean_confidence": 0.95,
                        "raw_data": {},
                        "processing_mode": "pdf_text_layer",
                    }
        except Exception:
            pass

    # Fallback: render pages to images + Tesseract
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))

        all_texts: list[str] = []
        all_confidences: list[int] = []

        for page_num in range(min(len(doc), 3)):  # Process up to 3 pages
            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            if _cv2_available:
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                elif pix.n == 4:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)

                if doc_type:
                    from services.ocr_service.preprocessor import preprocess_for_doctype
                    img_array = preprocess_for_doctype(img_array, doc_type)

                page_result = _run_with_retry(img_array, doc_type)
            elif _pil_available:
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                page_result = _run_with_retry(img, doc_type)
            else:
                continue

            if page_result.get("text", "").strip():
                all_texts.append(page_result["text"])
                all_confidences.extend(page_result.get("word_confidences", []))

        if all_texts:
            combined_text = "\n\n".join(all_texts)
            mean_conf = (sum(all_confidences) / len(all_confidences) / 100.0) if all_confidences else 0.0
            return {
                "text": combined_text,
                "word_confidences": all_confidences[:200],  # cap for response size
                "mean_confidence": round(mean_conf, 3),
                "raw_data": {},
                "processing_mode": "pdf_tesseract_render",
            }
    except Exception:
        pass

    return {"text": "", "word_confidences": [], "mean_confidence": 0.0, "raw_data": {}, "processing_mode": "pdf_failed"}


def extract(file_path: str | Path, doc_type: str | None = None) -> dict[str, Any]:
    """
    Main entry point. Auto-detects PDF vs image.
    Returns: { text, word_confidences, mean_confidence, raw_data, processing_mode }
    """
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _extract_from_pdf(path, doc_type=doc_type)
    return _extract_from_image_file(path, doc_type=doc_type)
