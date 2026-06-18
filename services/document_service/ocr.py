import pytesseract
import os
from dotenv import load_dotenv
from services.document_service.preprocess import preprocess

load_dotenv("config/.env")
tesseract_path = os.getenv("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

def extract_text(file_path: str) -> str:
    """
    Run full preprocessing then extract raw text from image.
    Returns plain string of all text found.
    """
    img = preprocess(file_path)
    text = pytesseract.image_to_string(img)
    return text

def extract_text_with_confidence(file_path: str) -> dict:
    """
    Extract text and return alongside confidence score.
    """
    img = preprocess(file_path)
    text = pytesseract.image_to_string(img)
    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT
    )
    confidences = [
        int(c) for c in data['conf']
        if str(c).isdigit() and int(c) > 0
    ]
    avg_confidence = round(
        sum(confidences) / len(confidences) / 100, 3
    ) if confidences else 0.0

    return {
        "text": text,
        "confidence": avg_confidence
    }