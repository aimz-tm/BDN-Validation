"""
OCR preprocessor — Phase 1 (improved).
Two preprocessing modes driven by doc_type from classifier:
  - preprocess_digital    : upscale if too small, Otsu binarization, mild contrast
  - preprocess_handwritten: reduced denoising (avoids over-smoothing strokes),
                            sharpening after denoise, adaptive threshold
All parameters from config.yaml.
"""

from __future__ import annotations

import numpy as np

try:
    import cv2  # type: ignore
    _cv2_available = True
except ImportError:
    _cv2_available = False

from core.config_loader import get_config


def _grayscale(img: "np.ndarray") -> "np.ndarray":
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _upscale_if_small(img: "np.ndarray", min_height: int = 1400) -> "np.ndarray":
    """
    Upscale image if it is below the minimum height threshold.
    Tesseract performs best at ~300 DPI (A4 = ~3508px tall).
    Upscaling small/low-res scans dramatically improves OCR accuracy.
    Does NOT downscale large images.
    """
    if not _cv2_available:
        return img
    h = img.shape[0]
    if h < min_height:
        scale = min_height / h
        new_h = int(h * scale)
        new_w = int(img.shape[1] * scale)
        # INTER_CUBIC is best for upscaling text
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return img


def _deskew(img: "np.ndarray") -> "np.ndarray":
    """Rotate image to correct skew using Hough lines."""
    try:
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)
        if lines is None:
            return img
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 != x1:
                angles.append(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if not angles:
            return img
        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.5:
            return img
        h, w = img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), median_angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return img


def preprocess_digital(image: "np.ndarray") -> "np.ndarray":
    """
    Preprocessing for digital/printed BDNs.
    1. Upscale if image height < 1400px (handles low-res scans)
    2. Convert to grayscale
    3. Deskew
    4. Otsu binarization for clean printed text
    """
    if not _cv2_available:
        return image

    img = _upscale_if_small(image)
    gray = _grayscale(img)
    gray = _deskew(gray)

    # Otsu binarization — works well for high-contrast printed text
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def preprocess_handwritten(image: "np.ndarray") -> "np.ndarray":
    """
    Preprocessing for handwritten/scanned BDNs.
    1. Upscale if too small
    2. Grayscale + deskew
    3. Moderate denoising (h=10, not 15 — avoids over-smoothing strokes)
    4. Sharpening to recover stroke edges lost during denoising
    5. Adaptive threshold — handles uneven lighting and ink variation
    6. Morphological cleanup
    """
    if not _cv2_available:
        return image

    cfg = get_config().get("classifier", {})

    img = _upscale_if_small(image)
    gray = _grayscale(img)
    gray = _deskew(gray)

    # Moderate denoising — h=10 preserves stroke edges better than h=15
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # Sharpening kernel to recover edges lost during denoising
    sharpen_kernel = np.array([
        [ 0, -1,  0],
        [-1,  5, -1],
        [ 0, -1,  0],
    ], dtype=np.float32)
    sharpened = cv2.filter2D(denoised, -1, sharpen_kernel)
    # Clip to valid range
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # Adaptive threshold — better than Otsu for handwritten/uneven ink
    binary = cv2.adaptiveThreshold(
        sharpened, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15, C=8,
    )

    # Morphological cleanup: close small gaps in strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return cleaned


def preprocess_for_doctype(image: "np.ndarray", doc_type: str) -> "np.ndarray":
    """Route to correct preprocessor based on doc_type."""
    if doc_type == "HANDWRITTEN":
        return preprocess_handwritten(image)
    return preprocess_digital(image)
