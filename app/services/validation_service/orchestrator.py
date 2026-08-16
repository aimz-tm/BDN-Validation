"""
Full BDN validation orchestrator — Phase 10 refactor.
Runs all services in order:
  1. OCR (engine + classifier)
  2. Extraction (routing to digital/handwritten extractor)
  3. Credibility (scorer + duplicate checker)
  4. Vessel Verification (resolver + datalastic)
  5. Barge Verification (resolver + mpa registry)
  6. Location / AIS (fetcher + feature builder + ML scorer)
  7. Fraud Detection (detector)
  8. Scoring (6-dimensional + audit trail)
  9. Report (generator)
Always returns a verdict dict. Never raises.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config_loader import get_config
from app.services.document_service.highlights import build_field_highlights
from app.services.validation_service.logistics import build_validation_logistics
from app.stub.mock_pipeline import run_mock_validation


def _transaction_id() -> str:
    year = datetime.now(timezone.utc).year
    return f"BDN-{year}-{uuid.uuid4().hex[:6].upper()}"


def _attach_document_assets(
    verdict: dict[str, Any],
    file_path: str | Path,
    *,
    preview_url: str | None,
    content_type: str | None,
    filename: str | None,
) -> dict[str, Any]:
    path = Path(file_path)
    displayable = path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

    document_meta: dict[str, Any] = {
        "preview_url": preview_url,
        "filename": filename,
        "content_type": content_type,
        "is_image": displayable,
    }

    if displayable and path.exists():
        try:
            document_meta["field_highlights"] = build_field_highlights(
                str(path),
                verdict.get("extraction") or {},
                ocr_result=verdict.get("_ocr_result"),   # reuse existing OCR data
            )
        except Exception as exc:
            document_meta["highlight_error"] = str(exc)

    verdict["document"] = document_meta
    if preview_url:
        verdict["preview_url"] = preview_url

    try:
        verdict["validation_logistics"] = build_validation_logistics(verdict)
    except Exception as exc:
        verdict["validation_logistics"] = [
            {"category": "System", "check": "Logistics summary", "status": "unknown", "detail": str(exc)}
        ]

    return verdict


def run_validation(
    file_path: str | Path,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    preview_url: str | None = None,
    dev_scenario: str | None = None,
) -> dict[str, Any]:
    """
    Execute full validation pipeline. Never raises — returns verdict dict.
    dev_scenario forces mock AIS behaviour (valid | ais_unavailable | barge_missing).
    """
    config = get_config()
    path = Path(file_path)

    if config.get("pipeline", {}).get("use_mock") and not config.get("pipeline", {}).get("use_orchestrator", True):
        verdict = run_mock_validation(filename=filename, scenario=dev_scenario)
        return _attach_document_assets(
            verdict, path, preview_url=preview_url, content_type=content_type, filename=filename
        )

    try:
        # ── PHASE 1: OCR ─────────────────────────────────────────────
        from app.services.ocr_service.engine import extract as ocr_extract
        from app.services.ocr_service.classifier import classify as ocr_classify

        # Pass 1: Raw extraction to determine document type
        ocr_result = ocr_extract(str(path))
        classification_result = ocr_classify(str(path), ocr_result)
        doc_type = classification_result.get("doc_type", "DIGITAL")
        doc_type_confidence = float(classification_result.get("confidence", 0.9))

        # Pass 2: Re-run extraction with proper preprocessing if image
        # (PDFs with native text layers don't need this)
        if classification_result.get("processing_mode") != "pdf_text_layer":
            ocr_result = ocr_extract(str(path), doc_type=doc_type)

        # ── PHASE 2: Extraction ──────────────────────────────────────
        from app.services.extraction_service.extractor import extract_fields
        extraction = extract_fields(str(path), ocr_result=ocr_result, doc_type=doc_type)
        extraction["doc_type"] = doc_type

        # ── PHASE 2b: Misclassification recovery ─────────────────────
        # If classified DIGITAL but extraction confidence is poor, retry with
        # HANDWRITTEN preprocessing. Use whichever pass yields higher confidence.
        if doc_type == "DIGITAL" and float(extraction.get("extraction_confidence", 1.0)) < 0.40:
            ocr_result_hw = ocr_extract(str(path), doc_type="HANDWRITTEN")
            extraction_hw = extract_fields(str(path), ocr_result=ocr_result_hw, doc_type="HANDWRITTEN")
            if float(extraction_hw.get("extraction_confidence", 0)) > float(extraction.get("extraction_confidence", 0)) + 0.08:
                doc_type = "HANDWRITTEN"
                ocr_result = ocr_result_hw
                extraction = extraction_hw
                extraction["doc_type"] = "HANDWRITTEN"

        # ── PHASE 3: Credibility ─────────────────────────────────────
        from app.services.credibility_service.scorer import check_credibility
        credibility = check_credibility(extraction)

        # ── PHASE 4: Vessel Verification ──────────────────────────────
        from app.services.vessel_verification_service.resolver import resolve_vessel_identity
        identity = resolve_vessel_identity(extraction)

        # ── PHASE 5: Barge Verification ───────────────────────────────
        from app.services.barge_verification_service.resolver import resolve_barge_identity
        # Get port coordinates for inradius fallback
        from app.services.timezone_service.converter import delivery_window_utc
        window = delivery_window_utc(extraction)
        barge = resolve_barge_identity(
            barge_name=extraction.get("barge_name"),
            sb_number=extraction.get("barge_sb_number"),
            vessel_lat=window.get("port_lat"),
            vessel_lon=window.get("port_lon"),
            delivery_start=window.get("start_utc"),
            delivery_end=window.get("end_utc"),
        )

        # ── PHASE 6: AIS / Location ───────────────────────────────────
        ais_scenario = dev_scenario if config.get("pipeline", {}).get("allow_dev_scenario") else None
        if config.get("pipeline", {}).get("mock_ais", True):
            from app.stub.mock_ais import get_mock_ais_validation
            ais = get_mock_ais_validation(identity, extraction, scenario=ais_scenario)
        else:
            from app.services.ais_service.validate import run_ais_validation
            ais = run_ais_validation(identity, extraction, dev_scenario=ais_scenario)

        # ── PHASE 7: Fraud Detection ──────────────────────────────────
        from app.services.fraud_service.detector import detect_fraud
        fraud = detect_fraud(
            credibility_flags=credibility.get("credibility_flags") or [],
            identity=identity,
            barge=barge,
            ais=ais,
            extraction=extraction,
        )

        # ── PHASE 8: Scoring ──────────────────────────────────────────
        from app.services.scoring_service.scorer import compute_score
        score = compute_score(
            ocr_confidence=float(extraction.get("ocr_confidence") or 0.0),
            extraction_confidence=float(extraction.get("extraction_confidence") or 0.0),
            identity=identity,
            barge=barge,
            ais=ais,
            credibility_flags=credibility.get("credibility_flags") or [],
            fraud_result=fraud,
        )

        # ── PHASE 9: Report ───────────────────────────────────────────
        from app.services.report_service.generator import generate_report
        verdict = generate_report(
            transaction_id=_transaction_id(),
            doc_type=doc_type,
            doc_type_confidence=doc_type_confidence,
            extracted_fields=extraction,
            credibility=credibility,
            identity=identity,
            barge=barge,
            ais=ais,
            fraud=fraud,
            score=score,
            upload_filename=filename,
            preview_url=preview_url,
        )
        verdict["_ocr_result"] = ocr_result   # carry for highlights reuse

        return _attach_document_assets(
            verdict, path, preview_url=preview_url, content_type=content_type, filename=filename
        )

    except Exception as exc:
        fallback = run_mock_validation(filename=filename, scenario="ais_unavailable")
        fallback["transaction_id"] = _transaction_id()
        fallback["verdict_reason"] = f"Pipeline error (partial result): {exc}"
        fallback["anomaly_flags"] = list(
            dict.fromkeys((fallback.get("anomaly_flags") or []) + ["pipeline_error"])
        )
        fallback["source"] = "error_fallback"
        return _attach_document_assets(
            fallback, path, preview_url=preview_url, content_type=content_type, filename=filename
        )
