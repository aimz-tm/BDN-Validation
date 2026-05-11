import cv2
import numpy as np
import pytesseract
import os
from dotenv import load_dotenv
from services.document_service.preprocess import load_image, to_grayscale

load_dotenv("config/.env")
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")


def get_edge_density(img_gray: np.ndarray) -> float:
    """
    Measure edge density using Canny edge detection.
    Handwritten docs have more irregular edges than digital.
    """
    edges = cv2.Canny(img_gray, 50, 150)
    return round(np.sum(edges > 0) / edges.size, 4)


def get_font_variance(file_path: str) -> float:
    """
    Measure variance in character confidence scores.
    Digital docs have consistent confidence — low variance.
    Handwritten/scanned docs have high variance.
    """
    img = load_image(file_path)
    gray = to_grayscale(img)
    data = pytesseract.image_to_data(
        gray, output_type=pytesseract.Output.DICT
    )
    confidences = [
        int(c) for c in data['conf']
        if str(c).isdigit() and int(c) > 0
    ]
    if len(confidences) < 5:
        return 100.0
    return round(float(np.var(confidences)), 2)


def classify_document(file_path: str) -> dict:
    """
    Classify BDN as DIGITAL, SCANNED, or HANDWRITTEN.

    Heuristic rules:
    - DIGITAL:      high OCR confidence + low font variance
    - SCANNED:      medium confidence OR high edge density
    - HANDWRITTEN:  low confidence + very high font variance
    """
    img = load_image(file_path)
    gray = to_grayscale(img)

    # OCR confidence
    data = pytesseract.image_to_data(
        gray, output_type=pytesseract.Output.DICT
    )
    confidences = [
        int(c) for c in data['conf']
        if str(c).isdigit() and int(c) > 0
    ]
    avg_conf = round(
        sum(confidences) / len(confidences) / 100, 3
    ) if confidences else 0.0

    edge_density  = get_edge_density(gray)
    font_variance = get_font_variance(file_path)

    # Classification logic
    if avg_conf >= 0.85 and font_variance < 300:
        doc_type = "DIGITAL"
    elif avg_conf >= 0.60 or edge_density > 0.05:
        doc_type = "SCANNED"
    else:
        doc_type = "HANDWRITTEN"

    return {
        "doc_type":       doc_type,
        "ocr_confidence": avg_conf,
        "edge_density":   edge_density,
        "font_variance":  font_variance
    }