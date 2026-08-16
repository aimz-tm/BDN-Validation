from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytesseract
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.config_loader import get_config, reload_config, save_config
from app.persistence.repository import get_transaction_db, list_transactions_db, persist_verdict
from app.persistence.memory_store import transaction_store
from app.stub.mock_pipeline import run_mock_validation, seed_transactions

load_dotenv("config/.env")

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

tesseract_path = os.getenv("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}


def _pipeline_mode_label() -> str:
    pipe = get_config().get("pipeline", {})
    if pipe.get("use_mock"):
        return "mock"
    if pipe.get("mock_ais", True):
        return "live (mock AIS)"
    return "live"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not transaction_store.list_all():
        transaction_store.seed(seed_transactions())
    yield


app = FastAPI(
    title="129Knots BDN Validation System",
    description="BDN fraud detection and validation using AIS telemetry",
    version="1.0.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ConfigUpdate(BaseModel):
    config: dict[str, Any]


def _db_ok() -> bool:
    try:
        from sqlalchemy import text
        from app.db.session import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _model_loaded() -> bool:
    config = get_config()
    path = BASE_DIR / config.get("model", {}).get("artifact_path", "models_ml/isolation_forest.pkl")
    return path.exists()


@app.get("/")
def dashboard():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "system": "129Knots BDN Validation System",
        "dashboard": "static/index.html not found — run Phase 0 static setup",
    }


@app.get("/health")
def health():
    config = get_config()
    tesseract_version = None
    try:
        version = pytesseract.get_tesseract_version()
        tesseract_version = f"{version.major}.{version.minor}.{version.micro}"
    except Exception as exc:
        tesseract_version = f"unavailable ({exc})"

    return {
        "status": "ok",
        "config_loaded": bool(config),
        "tesseract": tesseract_version,
        "database_connected": _db_ok(),
        "model_loaded": _model_loaded(),
        "pipeline_mode": _pipeline_mode_label(),
    }


@app.get("/config")
def read_config():
    return get_config()


@app.put("/config")
def update_config(body: ConfigUpdate):
    try:
        updated = save_config(body.config)
        reload_config()
        return {"status": "saved", "config": updated}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/validate")
async def validate_bdn(
    file: UploadFile = File(...),
    scenario: str | None = Query(
        None,
        description="Mock scenario: valid | unresolved | ais_unavailable",
    ),
):
    """
    Upload a BDN and run the full validation pipeline (document + identity + AIS + scoring).
    Set pipeline.use_mock=true in config to restore Phase 0 all-mock behaviour.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {sorted(ALLOWED_TYPES)}",
        )

    temp_path = BASE_DIR / f"temp_{file.filename}"
    try:
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        from app.services.document_service.pdf_utils import prepare_upload
        from app.services.validation_service.orchestrator import run_validation

        prep = prepare_upload(
            temp_path,
            STATIC_DIR / "uploads",
            file.filename,
            file.content_type,
        )

        verdict = run_validation(
            str(prep.ocr_path),
            filename=file.filename,
            content_type=file.content_type,
            preview_url=prep.preview_url,
            dev_scenario=scenario,
        )

        transaction_store.save(verdict)
        persisted = persist_verdict(verdict)
        verdict["persisted_to_db"] = persisted
        return verdict
    except HTTPException:
        raise
    except Exception as exc:
        from app.services.validation_service.orchestrator import run_validation

        try:
            from app.services.document_service.pdf_utils import prepare_upload

            prep = prepare_upload(
                temp_path,
                STATIC_DIR / "uploads",
                file.filename,
                file.content_type,
            )
            verdict = run_validation(
                str(prep.ocr_path),
                filename=file.filename,
                content_type=file.content_type,
                preview_url=prep.preview_url,
                dev_scenario="ais_unavailable",
            )
            verdict["verdict_reason"] = f"Validation encountered an error: {exc}. {verdict.get('verdict_reason', '')}"
            verdict["anomaly_flags"] = list(
                dict.fromkeys((verdict.get("anomaly_flags") or []) + ["pipeline_error"])
            )
        except Exception:
            verdict = run_mock_validation(filename=file.filename, scenario="ais_unavailable")
            verdict["verdict_reason"] = f"Validation encountered an error: {exc}"
            verdict["anomaly_flags"] = ["pipeline_error"]
        transaction_store.save(verdict)
        verdict["persisted_to_db"] = persist_verdict(verdict)
        return verdict
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.get("/transactions")
def list_transactions(
    human_review_only: bool = Query(False),
    classification: str | None = Query(None),
):
    db_rows = list_transactions_db(
        human_review_only=human_review_only,
        classification=classification,
    )
    if db_rows:
        return {"count": len(db_rows), "transactions": db_rows}

    rows = transaction_store.list_all(
        human_review_only=human_review_only,
        classification=classification,
    )
    return {
        "count": len(rows),
        "transactions": [
            {
                "transaction_id": r["transaction_id"],
                "classification": r["classification"],
                "confidence": r["confidence"],
                "human_review_required": r.get("human_review_required", False),
                "validated_at": r.get("validated_at"),
                "upload_filename": r.get("upload_filename"),
                "vessel_name": (r.get("extraction") or {}).get("vessel_name"),
                "imo": (r.get("identity_resolution") or {}).get("confirmed_imo")
                or (r.get("extraction") or {}).get("imo"),
                "port": (r.get("extraction") or {}).get("port"),
                "verdict_reason": r.get("verdict_reason"),
                "barge_missing": bool(r.get("barge_missing", False)),
            }
            for r in rows
        ],
    }


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):
    db_row = get_transaction_db(transaction_id)
    if db_row:
        return db_row

    row = transaction_store.get(transaction_id)
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return row


@app.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, body: dict[str, Any]):
    row = transaction_store.get(transaction_id)
    if not row and _db_ok():
        row = get_transaction_db(transaction_id)

    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    row.update(body)
    transaction_store.save(row)

    if _db_ok():
        try:
            from sqlalchemy import select
            from app.db.session import SessionLocal
            from app.models.database import Transaction
            
            def _safe_float(val: Any) -> float | None:
                try:
                    return float(val) if val is not None else None
                except (TypeError, ValueError):
                    return None

            with SessionLocal() as db:
                tx = db.scalar(
                    select(Transaction).where(Transaction.transaction_reference == transaction_id)
                )
                if tx:
                    ext = body.get("extraction") or {}
                    tx.classification = body.get("classification")
                    tx.confidence = _safe_float(body.get("confidence"))
                    tx.extracted_fields = ext
                    # Merge into existing validation_result so full payload is preserved
                    existing = tx.validation_result or {}
                    merged = {**existing, **body}
                    tx.validation_result = merged
                    tx.verdict_reason = body.get("verdict_reason")
                    tx.port = ext.get("port")
                    tx.quantity_mt = _safe_float(ext.get("quantity_mt"))
                    tx.density = _safe_float(ext.get("density"))
                    tx.sulphur_content = _safe_float(ext.get("sulphur_content"))
                    tx.flashpoint = _safe_float(ext.get("flashpoint"))
                    tx.supplier = ext.get("supplier")
                    db.commit()
                else:
                    logger.warning(
                        "update_transaction: no DB row found for transaction_reference=%s "
                        "— review-queue status change was only persisted in memory",
                        transaction_id,
                    )
        except Exception:
            logger.exception(
                "update_transaction: failed to persist DB update for transaction_id=%s",
                transaction_id,
            )

    return row


@app.get("/vessels/{imo}")
def get_vessel(imo: str):
    if not imo.isdigit() or len(imo) != 7:
        raise HTTPException(status_code=400, detail="IMO must be exactly 7 digits")

    for row in transaction_store.list_all():
        identity = row.get("identity_resolution") or {}
        if identity.get("confirmed_imo") == imo or (row.get("extraction") or {}).get("imo") == imo:
            return {
                "imo": imo,
                "name": identity.get("confirmed_name") or (row.get("extraction") or {}).get("vessel_name"),
                "mmsi": identity.get("confirmed_mmsi"),
                "resolution_method": identity.get("resolution_method"),
                "identity_confidence": identity.get("identity_confidence"),
                "flags": identity.get("flags", []),
                "last_transaction_id": row["transaction_id"],
            }

    from app.services.identity_service import registry_fallback

    vessel = registry_fallback.get_vessel_by_imo(imo)
    if vessel:
        return {
            "imo": imo,
            "name": vessel.get("name"),
            "mmsi": vessel.get("mmsi"),
            "resolution_method": "local_registry",
            "identity_confidence": 0.9,
            "flags": [],
            "last_transaction_id": None,
        }

    raise HTTPException(status_code=404, detail="Vessel not found in registry")



@app.post("/ocr/extract")
async def ocr_extract_endpoint(file: UploadFile = File(...)):
    """Phase 1 — OCR Service. Extract text and classify doc type from a BDN file."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    temp_path = BASE_DIR / f"temp_{file.filename}"
    with temp_path.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)
    try:
        from app.services.ocr_service.engine import extract as ocr_engine
        from app.services.ocr_service.classifier import classify as ocr_classify
        ocr_result = ocr_engine(str(temp_path))
        classification = ocr_classify(str(temp_path), ocr_result)
        return {
            "doc_type": classification.get("doc_type"),
            "doc_type_confidence": classification.get("confidence"),
            "doc_type_variance": classification.get("variance"),
            "text": ocr_result.get("text", "")[:2000],  # Truncate for API response
            "ocr_confidence": ocr_result.get("mean_confidence"),
            "word_confidences": ocr_result.get("word_confidences", [])[:50],
            "processing_mode": ocr_result.get("processing_mode"),
        }
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.post("/extraction/extract")
async def extraction_extract_endpoint(file: UploadFile = File(...)):
    """Phase 2 — Extraction Service. Extract all BDN fields with fuzzy matching."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    temp_path = BASE_DIR / f"temp_{file.filename}"
    with temp_path.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)
    try:
        from app.services.ocr_service.engine import extract as ocr_engine
        from app.services.ocr_service.classifier import classify as ocr_classify
        from app.services.extraction_service.extractor import extract_fields
        ocr_result = ocr_engine(str(temp_path))
        classification = ocr_classify(str(temp_path), ocr_result)
        doc_type = classification.get("doc_type", "DIGITAL")
        fields = extract_fields(str(temp_path), ocr_result=ocr_result, doc_type=doc_type)
        fields.pop("raw_text", None)  # Too large for API response
        return {"doc_type": doc_type, **fields}
    finally:
        if temp_path.exists():
            temp_path.unlink()


class VesselVerifyRequest(BaseModel):
    imo: str | None = None
    vessel_name: str | None = None


class BargeVerifyRequest(BaseModel):
    barge_name: str | None = None
    sb_number: str | None = None
    vessel_lat: float | None = None
    vessel_lon: float | None = None


class GeoVerifyRequest(BaseModel):
    confirmed_mmsi: str | None = None
    barge_mmsi: str | None = None
    start_time_utc: str | None = None
    end_time_utc: str | None = None
    port: str | None = None
    quantity_mt: float | None = None


@app.post("/verify/vessel")
def verify_vessel(body: VesselVerifyRequest):
    """Phase 4 — Vessel Verification Service."""
    from app.services.vessel_verification_service.resolver import resolve_vessel_identity
    extraction = {"vessel_name": body.vessel_name, "imo": body.imo}
    return resolve_vessel_identity(extraction)


@app.post("/verify/barge")
def verify_barge(body: BargeVerifyRequest):
    """Phase 5 — Barge Verification Service."""
    from app.services.barge_verification_service.resolver import resolve_barge_identity
    return resolve_barge_identity(
        barge_name=body.barge_name,
        sb_number=body.sb_number,
        vessel_lat=body.vessel_lat,
        vessel_lon=body.vessel_lon,
    )


@app.post("/verify/geolocation")
def verify_geolocation(body: GeoVerifyRequest):
    """Phase 6 — Location Verification Service."""
    from app.services.ais_service.validate import run_ais_validation
    identity = {"confirmed_mmsi": body.confirmed_mmsi, "vessel_identity_unresolved": False}
    extraction = {"port": body.port, "quantity_mt": body.quantity_mt,
                  "start_time": body.start_time_utc, "end_time": body.end_time_utc}
    return run_ais_validation(identity, extraction)

