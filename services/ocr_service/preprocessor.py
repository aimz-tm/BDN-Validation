"""
OCR preprocessor — Phase 1.

Preprocessing pipeline per document type:
  DIGITAL    : border crop → upscale → grayscale → deskew → CLAHE → Otsu binarise
  HANDWRITTEN: border crop → upscale → grayscale → deskew → CLAHE → denoise →
               sharpen → adaptive threshold → morph cleanup
"""

from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore
    _cv2_available = True
except ImportError:
    _cv2_available = False

from core.config_loader import get_config


# ── Helpers ────────────────────────────────────────────────────────────────────

def _grayscale(img: "np.ndarray") -> "np.ndarray":
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _upscale_if_small(img: "np.ndarray", min_height: int = 1400) -> "np.ndarray":
    """
    Upscale image if below minimum height.
    Tesseract performs best at ~300 DPI (A4 ≈ 3508 px tall).
    INTER_CUBIC is best for upscaling text.
    """
    h = img.shape[0]
    if h < min_height:
        scale = min_height / h
        new_h = int(h * scale)
        new_w = int(img.shape[1] * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return img


def _remove_borders(img: "np.ndarray") -> "np.ndarray":
    """
    Crop dark scan borders and shadow gradients at page edges.

    Strategy: threshold to find the bright (page) region, find its bounding
    rectangle, and crop to it with a small margin. Falls back to original
    image if the detected crop is unreasonably small (< 60 % of original).
    """
    try:
        # Invert: dark borders become white, page becomes dark — then find
        # the largest contour which should be the page content area.
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Find connected components of the bright (page) area
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img
        # Use the largest contour's bounding rect as the page boundary
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        orig_h, orig_w = img.shape[:2]
        # Sanity: reject crop if it removes more than 40 % of the image
        if w < orig_w * 0.6 or h < orig_h * 0.6:
            return img
        margin = 10
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(orig_w, x + w + margin)
        y2 = min(orig_h, y + h + margin)
        return img[y1:y2, x1:x2]
    except Exception:
        return img


def _deskew(img: "np.ndarray") -> "np.ndarray":
    """
    Correct skew using Hough line detection.

    Key fix over the previous version: filter to near-horizontal lines only
    (angle within ±15° of 0°) before computing the median. The old version
    included vertical table borders and diagonal lines, which pulled the
    estimated angle far off and rotated documents in the wrong direction.
    """
    try:
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=80,
            minLineLength=img.shape[1] // 6,  # line must span at least 1/6 of width
            maxLineGap=20,
        )
        if lines is None:
            return img

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 == x1:
                continue  # skip perfectly vertical lines
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only keep near-horizontal lines (±15°) — table borders are ~90°
            if abs(angle) <= 15.0:
                angles.append(angle)

        if not angles:
            return img

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.3:  # sub-0.3° skew is imperceptible
            return img

        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
        return cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception:
        return img


def _clahe(img: "np.ndarray") -> "np.ndarray":
    """
    Contrast Limited Adaptive Histogram Equalisation.

    Normalises local contrast across the image — the single most effective
    step for faded ink, photocopies, and uneven scan lighting. Works on
    grayscale images only.
    """
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(img)
    except Exception:
        return img


# ── Public preprocessors ───────────────────────────────────────────────────────

def preprocess_digital(image: "np.ndarray") -> "np.ndarray":
    """
    Pipeline for digital/printed BDNs:
      border crop → upscale → grayscale → deskew → CLAHE → Otsu binarise
    """
    if not _cv2_available:
        return image

    img = _upscale_if_small(image)
    gray = _grayscale(img)
    gray = _remove_borders(gray)
    gray = _deskew(gray)
    gray = _clahe(gray)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def preprocess_handwritten(image: "np.ndarray") -> "np.ndarray":
    """
    Pipeline for handwritten/scanned BDNs:
      border crop → upscale → grayscale → deskew → CLAHE →
      denoise → sharpen → adaptive threshold → morph cleanup
    """
    if not _cv2_available:
        return image

    img = _upscale_if_small(image)
    gray = _grayscale(img)
    gray = _remove_borders(gray)
    gray = _deskew(gray)
    gray = _clahe(gray)

    # Fast denoising: median blur removes salt-and-pepper noise without
    # the O(n²) cost of fastNlMeansDenoising (which takes 10-30 s on A4 300 DPI).
    denoised = cv2.medianBlur(gray, 3)

    # Mild sharpening to recover ink stroke edges
    sharpen_kernel = np.array([
        [ 0, -1,  0],
        [-1,  5, -1],
        [ 0, -1,  0],
    ], dtype=np.float32)
    sharpened = cv2.filter2D(denoised, -1, sharpen_kernel)
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # Adaptive threshold — larger blockSize handles bigger ink/lighting variations
    binary = cv2.adaptiveThreshold(
        sharpened, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=21, C=10,
    )

    # Morphological close: fill small gaps in pen strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return cleaned


def preprocess_for_doctype(image: "np.ndarray", doc_type: str) -> "np.ndarray":
    """Route to correct preprocessor based on doc_type."""
    if doc_type == "HANDWRITTEN":
        return preprocess_handwritten(image)
    return preprocess_digital(image)
