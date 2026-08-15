import os

import cv2
import numpy as np
import pytesseract
from dotenv import load_dotenv

from core.config_loader import get_config
from services.document_service.preprocess import load_image, to_grayscale

load_dotenv("config/.env")
tesseract_path = os.getenv("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


def _classifier_config() -> dict:
    return get_config()["classifier"]


def get_edge_density(img_gray: np.ndarray) -> float:
    cfg = _classifier_config()
    low = int(cfg["canny_low_threshold"])
    high = int(cfg["canny_high_threshold"])
    edges = cv2.Canny(img_gray, low, high)
    return round(float(np.sum(edges > 0) / edges.size), 4)


def get_font_variance(file_path: str) -> float:
    cfg = _classifier_config()
    img = load_image(file_path)
    gray = to_grayscale(img)
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in data["conf"] if str(c).isdigit() and int(c) > 0]
    if len(confidences) < int(cfg["min_confidence_samples"]):
        return float(cfg["empty_confidence_variance"])
    return round(float(np.var(confidences)), 2)


def classify_document(file_path: str) -> dict:
    """
    Classify BDN as DIGITAL, SCANNED, or HANDWRITTEN using config-driven thresholds.
    """
    cfg = _classifier_config()
    img = load_image(file_path)
    gray = to_grayscale(img)

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in data["conf"] if str(c).isdigit() and int(c) > 0]
    avg_conf = round(sum(confidences) / len(confidences) / 100, 3) if confidences else 0.0

    edge_density = get_edge_density(gray)
    font_variance = get_font_variance(file_path)

    digital_min_conf = float(cfg["digital_min_confidence"])
    digital_max_var = float(cfg["digital_max_font_variance"])
    scanned_min_conf = float(cfg["scanned_min_confidence"])
    scanned_min_edge = float(cfg["scanned_min_edge_density"])

    if avg_conf >= digital_min_conf and font_variance < digital_max_var:
        doc_type = "DIGITAL"
    elif avg_conf >= scanned_min_conf or edge_density > scanned_min_edge:
        doc_type = "SCANNED"
    else:
        doc_type = "HANDWRITTEN"

    return {
        "doc_type": doc_type,
        "ocr_confidence": avg_conf,
        "edge_density": edge_density,
        "font_variance": font_variance,
    }
