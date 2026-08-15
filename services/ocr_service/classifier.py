"""
Document classifier — Phase 1.
DIGITAL: PDF with extractable text layer (>50 chars).
HANDWRITTEN: everything else.
Uses OCR confidence variance to confirm classification.
All thresholds from config.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_loader import get_config


def classify(file_path: str | Path, ocr_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Classify BDN as DIGITAL or HANDWRITTEN.
    Returns: { doc_type, confidence, variance, processing_mode }
    """
    path = Path(file_path)
    cfg = get_config().get("classifier", {})
    digital_conf_threshold = float(cfg.get("digital_min_confidence", 0.85))
    digital_font_variance = float(cfg.get("digital_max_font_variance", 300))
    min_samples = int(cfg.get("min_confidence_samples", 5))

    # PDFs with text layer are DIGITAL
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(str(path)) as pdf:
                text = "".join(page.extract_text() or "" for page in pdf.pages)
                if len(text.strip()) > 50:
                    return {
                        "doc_type": "DIGITAL",
                        "confidence": 0.98,
                        "variance": 0.0,
                        "processing_mode": "pdf_text_layer",
                    }
        except Exception:
            pass

    # Use OCR confidence variance to distinguish printed vs handwritten images
    if ocr_result:
        word_confs = ocr_result.get("word_confidences") or []
        mean_conf = float(ocr_result.get("mean_confidence") or 0.0)

        if len(word_confs) >= min_samples:
            import statistics
            variance = statistics.variance(word_confs) if len(word_confs) > 1 else 0.0
            high_variance_floor = float(cfg.get("handwritten_high_variance_floor", 400))

            # A document is only DIGITAL if confidence is high AND variance is low.
            # If variance is above the floor — even with decent average confidence — the
            # per-word confidence is too erratic for printed text: classify as HANDWRITTEN.
            is_digital = (
                mean_conf >= digital_conf_threshold
                and variance <= digital_font_variance
                and variance <= high_variance_floor
            )
            if is_digital:
                return {
                    "doc_type": "DIGITAL",
                    "confidence": round(mean_conf, 3),
                    "variance": round(variance, 1),
                    "processing_mode": "ocr_confidence",
                }
            else:
                return {
                    "doc_type": "HANDWRITTEN",
                    "confidence": round(1.0 - mean_conf, 3),
                    "variance": round(variance, 1),
                    "processing_mode": "ocr_confidence",
                }

    # Fallback: image files without OCR data → assume HANDWRITTEN
    return {
        "doc_type": "HANDWRITTEN",
        "confidence": 0.6,
        "variance": 0.0,
        "processing_mode": "fallback",
    }
