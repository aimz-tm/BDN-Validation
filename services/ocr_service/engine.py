"""
OCR engine — Phase 1.

Tesseract wrapper with:
  - Auto orientation detection (OSD) before extraction
  - CLAHE + border crop + deskew via preprocessor.py
  - Multi-PSM ensemble: tries PSM 3, 4, 6, 11 and keeps highest confidence
  - High-DPI PDF rendering (300 DPI)
  - Text output cleaning before returning to extractor
"""

from __future__ import annotations

import io
import re
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


# PSM modes tried in ensemble order per doc type.
# DIGITAL/unknown: printed forms benefit from PSM 6 (uniform block) and PSM 11 (sparse labels).
# HANDWRITTEN: PSM 4 (single column) and PSM 11 (sparse) — PSM 6 is for printed, not useful here.
_ENSEMBLE_PSMS = {
    "DIGITAL":     [6, 11, 4, 3],
    "HANDWRITTEN": [4, 11],        # two passes only — handwritten is inherently low-confidence
    None:          [3, 11, 6],     # classification pass: fast, no need for all modes
}

# Primary PSM by doc type — tried first; ensemble only runs if confidence is low
_PRIMARY_PSM = {
    "DIGITAL":     6,
    "HANDWRITTEN": 4,
    None:          3,
}

# Confidence threshold below which the ensemble is triggered.
# Handwritten OCR is inherently lower confidence — don't keep running PSMs just because
# we're at 0.60; only trigger the extra pass if it's genuinely bad (< 0.50).
_LOW_CONF_THRESHOLD = {
    "DIGITAL":     0.75,
    "HANDWRITTEN": 0.50,
    None:          0.65,
}


# ── Text cleaning ──────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """
    Clean raw Tesseract output before passing to the extractor.

    Tesseract produces several classes of noise that hurt regex and fuzzy
    matching:
      - Garbage characters from scan artefacts (|, ~, ^, `, ¢, §, ©, ®…)
      - Excessive blank lines (3+ consecutive newlines → 2)
      - Broken hyphenation at line ends (word- \n word → word word)
      - Leading/trailing whitespace on each line
    """
    if not text:
        return text

    # Remove known OCR garbage characters that are never in BDN fields
    # Square brackets are common artifacts where letters are misread (e.g. "[J" → " J")
    text = re.sub(r'[|~^`¢§©®°•†‡™℃℉\[\]]', ' ', text)

    # Fix broken hyphenation: "deliv-\nery" → "delivery"
    text = re.sub(r'-\s*\n\s*', '', text)

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.splitlines()]

    # Collapse 3+ consecutive blank lines to 2
    cleaned_lines: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


# ── Tesseract runners ──────────────────────────────────────────────────────────

def _tesseract_from_array(img_array: Any, psm: int = 6) -> dict[str, Any]:
    """Run Tesseract image_to_data — returns text + per-word confidence scores."""
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


def _auto_orient(img_array: Any) -> Any:
    """
    Detect document orientation with Tesseract OSD (--psm 0) and rotate to
    upright if needed. Handles 90 / 180 / 270 degree rotations — common for
    camera-photographed BDNs.

    Returns the (possibly rotated) image array. Falls back silently on any
    error so it never blocks the main pipeline.
    """
    if not (_tesseract_available and _cv2_available):
        return img_array
    try:
        osd = pytesseract.image_to_osd(img_array, config="--psm 0", output_type=pytesseract.Output.DICT)
        angle = int(osd.get("rotate", 0))
        if angle == 0:
            return img_array
        # cv2 rotates counter-clockwise; Tesseract OSD reports clockwise correction needed
        rotation_map = {90: cv2.ROTATE_90_COUNTERCLOCKWISE,
                        180: cv2.ROTATE_180,
                        270: cv2.ROTATE_90_CLOCKWISE}
        if angle in rotation_map:
            return cv2.rotate(img_array, rotation_map[angle])
        return img_array
    except Exception:
        return img_array


def _run_ensemble(img_array: Any, doc_type: str | None) -> dict[str, Any]:
    """
    Multi-PSM ensemble: try the primary PSM first.
    If confidence < threshold, try remaining PSMs and keep the best result.
    """
    primary_psm = _PRIMARY_PSM.get(doc_type, 3)
    best = _tesseract_from_array(img_array, psm=primary_psm)
    best["psm_used"] = primary_psm

    conf_threshold = _LOW_CONF_THRESHOLD.get(doc_type, 0.65)
    if best["mean_confidence"] >= conf_threshold:
        best["ensemble_tried"] = False
        return best

    ensemble_psms = _ENSEMBLE_PSMS.get(doc_type, [3, 11, 6])
    for psm in ensemble_psms:
        if psm == primary_psm:
            continue
        result = _tesseract_from_array(img_array, psm=psm)
        if result["mean_confidence"] > best["mean_confidence"]:
            best = result
            best["psm_used"] = psm

    best["ensemble_tried"] = True
    return best


# ── File-type extractors ───────────────────────────────────────────────────────

def _extract_from_image_file(file_path: Path, doc_type: str | None = None) -> dict[str, Any]:
    if _cv2_available:
        img = cv2.imread(str(file_path))
        if img is not None:
            img = _auto_orient(img)
            if doc_type:
                from services.ocr_service.preprocessor import preprocess_for_doctype
                img = preprocess_for_doctype(img, doc_type)
            result = _run_ensemble(img, doc_type)
            result["text"] = _clean_text(result["text"])
            result["processing_mode"] = "tesseract_image"
            return result

    if _pil_available:
        img = Image.open(file_path)
        result = _run_ensemble(img, doc_type)
        result["text"] = _clean_text(result["text"])
        result["processing_mode"] = "tesseract_pil"
        return result

    return {
        "text": "", "word_confidences": [], "mean_confidence": 0.0,
        "raw_data": {}, "processing_mode": "unavailable",
    }


def _extract_from_pdf(file_path: Path, doc_type: str | None = None) -> dict[str, Any]:
    """Try pdfplumber text layer first; fall back to Tesseract on rendered pages."""
    cfg = get_config().get("ocr", {})
    dpi = int(cfg.get("pdf_render_dpi", 300))

    # Text layer path (classification pass only — skip when doc_type is set)
    if _pdfplumber_available and not doc_type:
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                page_texts = []
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    if t.strip():
                        page_texts.append(t)
                combined = "\n\n".join(page_texts)
                if len(combined.strip()) > 50:
                    return {
                        "text": _clean_text(combined),
                        "word_confidences": [],
                        "mean_confidence": 0.95,
                        "raw_data": {},
                        "processing_mode": "pdf_text_layer",
                    }
        except Exception:
            pass

    # Render pages → images → Tesseract
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))

        all_texts: list[str] = []
        all_confidences: list[int] = []

        for page_num in range(min(len(doc), 3)):
            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            if _cv2_available:
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 3:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                elif pix.n == 4:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)

                img_array = _auto_orient(img_array)

                if doc_type:
                    from services.ocr_service.preprocessor import preprocess_for_doctype
                    img_array = preprocess_for_doctype(img_array, doc_type)

                page_result = _run_ensemble(img_array, doc_type)
            elif _pil_available:
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                page_result = _run_ensemble(img, doc_type)
            else:
                continue

            if page_result.get("text", "").strip():
                all_texts.append(page_result["text"])
                all_confidences.extend(page_result.get("word_confidences", []))

        if all_texts:
            combined_text = _clean_text("\n\n".join(all_texts))
            mean_conf = (
                sum(all_confidences) / len(all_confidences) / 100.0
            ) if all_confidences else 0.0
            return {
                "text": combined_text,
                "word_confidences": all_confidences[:200],
                "mean_confidence": round(mean_conf, 3),
                "raw_data": {},
                "processing_mode": "pdf_tesseract_render",
            }
    except Exception:
        pass

    return {
        "text": "", "word_confidences": [], "mean_confidence": 0.0,
        "raw_data": {}, "processing_mode": "pdf_failed",
    }


# ── Public entry point ─────────────────────────────────────────────────────────

def extract(file_path: str | Path, doc_type: str | None = None) -> dict[str, Any]:
    """
    Main entry point. Auto-detects PDF vs image.
    Returns: { text, word_confidences, mean_confidence, raw_data, processing_mode }
    """
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return _extract_from_pdf(path, doc_type=doc_type)
    return _extract_from_image_file(path, doc_type=doc_type)
