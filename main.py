from fastapi import FastAPI
from dotenv import load_dotenv
import yaml
import os
import pytesseract

# Load environment variables from config/.env
load_dotenv("config/.env")

# Load YAML config
with open("config/config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")

# Initialize FastAPI app
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