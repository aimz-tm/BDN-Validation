import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
from dotenv import load_dotenv

load_dotenv("config/.env")
tesseract_path = os.getenv("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def load_image(file_path: str) -> np.ndarray:
    """Load image from file path into OpenCV format (PDFs are rasterized first)."""
    from app.services.document_service.pdf_utils import document_image_source

    with document_image_source(file_path) as img_path:
        img = cv2.imread(str(img_path))
        if img is None:
            raise ValueError(f"Could not load image from {file_path}")
        return img

def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert to grayscale — removes colour noise."""
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def denoise(img: np.ndarray) -> np.ndarray:
    """Remove salt-and-pepper noise from scanned docs."""
    return cv2.fastNlMeansDenoising(img, h=10)

def threshold(img: np.ndarray) -> np.ndarray:
    """Adaptive threshold — handles uneven lighting across the page."""
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

def deskew(img: np.ndarray) -> np.ndarray:
    """Straighten tilted scans."""
    coords = np.column_stack(np.where(img > 0))
    if len(coords) == 0:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)

def preprocess(file_path: str) -> np.ndarray:
    """
    Full preprocessing pipeline.
    Returns cleaned image ready for Tesseract.
    """
    img = load_image(file_path)
    img = to_grayscale(img)
    img = denoise(img)
    img = threshold(img)
    img = deskew(img)
    return img

def get_ocr_confidence(file_path: str) -> float:
    """
    Run Tesseract and return average confidence score (0.0 to 1.0).
    Used by classifier and credibility engine.
    """
    img = preprocess(file_path)
    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT
    )
    confidences = [
        int(c) for c in data['conf'] if str(c).isdigit() and int(c) > 0
    ]
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences) / 100, 3)