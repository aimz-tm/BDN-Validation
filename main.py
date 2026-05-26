from fastapi import FastAPI, UploadFile, File, HTTPException
from dotenv import load_dotenv
import yaml
import os
import pytesseract
import shutil

load_dotenv("config/.env")

with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")

app = FastAPI(
    title="BDN Validation System",
    description="AI-assisted marine fuel transaction validation using AIS telemetry",
    version="0.1.0"
)

@app.get("/")
def root():
    return {
        "system": "BDN Validation System",
        "version": "0.1.0",
        "status": "running"
    }

@app.get("/health")
def health():
    version = pytesseract.get_tesseract_version()
    return {
        "status": "ok",
        "config_loaded": config is not None,
        "tesseract": f"{version.major}.{version.minor}.{version.micro}"
    }

@app.post("/extract")
async def extract_bdn(file: UploadFile = File(...)):
    """
    Upload a BDN image or PDF.
    Returns document classification, extracted fields, and credibility score.
    """
    allowed = ["image/png", "image/jpeg", "image/jpg", "application/pdf"]
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}"
        )

    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        from services.document_service.pipeline import process_bdn
        result = process_bdn(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return result