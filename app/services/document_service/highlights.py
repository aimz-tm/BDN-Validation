"""
Locate extracted BDN field values on the document image for UI highlighting.
Coordinates are normalized 0–1 relative to original image dimensions.
"""

from __future__ import annotations

import re
from typing import Any

import cv2
import pytesseract
from pytesseract import Output

from app.services.document_service.preprocess import preprocess

FIELD_LABELS = {
    "vessel_name": "Vessel name",
    "imo": "IMO",
    "barge_name": "Barge",
    "delivery_date": "Delivery date",
    "start_time": "Start time",
    "end_time": "End time",
    "port": "Port",
    "quantity_mt": "Quantity (MT)",
}

FIELD_KEYS = list(FIELD_LABELS.keys())


def _normalize_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _word_entries_from_raw(raw_data: dict, img_width: int, img_height: int) -> tuple[list[dict[str, Any]], int, int]:
    """Build word entries from already-computed Tesseract image_to_data output."""
    words: list[dict[str, Any]] = []
    n = len(raw_data.get("text", []))
    proc_w = img_width or 1
    proc_h = img_height or 1
    for i in range(n):
        text = (raw_data["text"][i] or "").strip()
        if not text:
            continue
        conf = raw_data["conf"][i]
        try:
            conf_int = int(conf)
        except (TypeError, ValueError):
            conf_int = -1
        if conf_int <= 0:
            continue
        left = int(raw_data["left"][i])
        top = int(raw_data["top"][i])
        w = int(raw_data["width"][i])
        h = int(raw_data["height"][i])
        words.append({
            "text": text,
            "norm": _normalize_token(text),
            "left": left / proc_w,
            "top": top / proc_h,
            "width": w / proc_w,
            "height": h / proc_h,
        })
    return words, img_width, img_height


def _word_entries(file_path: str) -> tuple[list[dict[str, Any]], int, int]:
    """Fallback: re-run Tesseract on the image (used when raw_data unavailable)."""
    original = cv2.imread(file_path)
    if original is None:
        raise ValueError(f"Could not read image: {file_path}")
    height, width = original.shape[:2]
    processed = preprocess(file_path)
    data = pytesseract.image_to_data(processed, output_type=Output.DICT)
    # Normalise using processed dimensions
    proc_h, proc_w = processed.shape[:2]
    words: list[dict[str, Any]] = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        conf = data["conf"][i]
        try:
            conf_int = int(conf)
        except (TypeError, ValueError):
            conf_int = -1
        if conf_int <= 0:
            continue
        left = int(data["left"][i])
        top = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        words.append({
            "text": text,
            "norm": _normalize_token(text),
            "left": left / proc_w,
            "top": top / proc_h,
            "width": w / proc_w,
            "height": h / proc_h,
        })
    return words, width, height


def _merge_boxes(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    if not boxes:
        return None
    x1 = min(b["left"] for b in boxes)
    y1 = min(b["top"] for b in boxes)
    x2 = max(b["left"] + b["width"] for b in boxes)
    y2 = max(b["top"] + b["height"] for b in boxes)
    return {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}


def _find_value_box(value: str, words: list[dict[str, Any]]) -> dict[str, float] | None:
    if value is None:
        return None

    if isinstance(value, float):
        value_str = f"{value:g}"
    else:
        value_str = str(value).strip()

    if not value_str:
        return None

    # IMO: single 7-digit token
    if re.fullmatch(r"\d{7}", value_str):
        for w in words:
            if w["norm"] == value_str:
                return {"left": w["left"], "top": w["top"], "width": w["width"], "height": w["height"]}
        return None

    tokens = [_normalize_token(t) for t in re.split(r"\s+", value_str) if t.strip()]
    if not tokens:
        return None

    norms = [w["norm"] for w in words if w["norm"]]
    for start in range(len(words)):
        if words[start]["norm"] != tokens[0]:
            continue
        matched = [words[start]]
        ti = 1
        wi = start + 1
        while ti < len(tokens) and wi < len(words):
            if words[wi]["norm"] == tokens[ti]:
                matched.append(words[wi])
                ti += 1
            wi += 1
        if ti == len(tokens):
            return _merge_boxes(matched)

    # Partial: longest token for vessel names etc.
    if len(tokens) == 1:
        best = None
        best_len = 0
        for w in words:
            if tokens[0] in w["norm"] or w["norm"] in tokens[0]:
                if len(w["norm"]) > best_len:
                    best_len = len(w["norm"])
                    best = w
        if best:
            return {"left": best["left"], "top": best["top"], "width": best["width"], "height": best["height"]}

    return None


def build_field_highlights(
    file_path: str,
    fields: dict[str, Any],
    ocr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return highlight regions for each extracted field.

    If ocr_result (from engine.extract) is passed in, reuses its raw_data
    to avoid a second Tesseract call (~2.5s saving).
    """
    try:
        raw_data = (ocr_result or {}).get("raw_data") or {}
        if raw_data and raw_data.get("text"):
            # Fast path: reuse existing OCR data
            original = cv2.imread(file_path)
            if original is not None:
                height, width = original.shape[:2]
            else:
                width, height = 1700, 2200  # Sensible default
            words, width, height = _word_entries_from_raw(raw_data, width, height)
        else:
            # Fallback: re-run Tesseract (PDF or missing raw_data)
            words, width, height = _word_entries(file_path)
    except Exception as exc:
        return {
            "image_width": 0,
            "image_height": 0,
            "highlights": [],
            "error": str(exc),
        }

    highlights: list[dict[str, Any]] = []
    for key in FIELD_KEYS:
        value = fields.get(key)
        box = _find_value_box(value, words) if value is not None else None
        entry: dict[str, Any] = {
            "field": key,
            "label": FIELD_LABELS[key],
            "value": value,
            "found_on_document": box is not None,
        }
        if box:
            entry.update({
                "x": round(box["left"], 4),
                "y": round(box["top"], 4),
                "w": round(box["width"], 4),
                "h": round(box["height"], 4),
            })
        highlights.append(entry)

    return {
        "image_width": width,
        "image_height": height,
        "highlights": highlights,
    }
