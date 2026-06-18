"""
Report generator — Phase 9.
Assembles final report object from all service outputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _transaction_id() -> str:
    year = datetime.now(timezone.utc).year
    return f"BDN-{year}-{uuid.uuid4().hex[:6].upper()}"


def generate_report(
    *,
    transaction_id: str | None = None,
    doc_type: str,
    doc_type_confidence: float,
    extracted_fields: dict[str, Any],
    credibility: dict[str, Any],
    identity: dict[str, Any],
    barge: dict[str, Any],
    ais: dict[str, Any],
    fraud: dict[str, Any],
    score: dict[str, Any],
    upload_filename: str | None = None,
    preview_url: str | None = None,
) -> dict[str, Any]:
    """
    Assemble complete validation report.
    This is the canonical output consumed by the dashboard and API.
    """
    tid = transaction_id or _transaction_id()

    # Collect all flags from all services
    all_credibility_flags = credibility.get("credibility_flags") or []
    all_anomaly_flags = list(ais.get("anomaly_flags") or [])
    if identity.get("vessel_identity_unresolved"):
        all_anomaly_flags.append("vessel_identity_unresolved")
    all_anomaly_flags = list(dict.fromkeys(all_anomaly_flags))

    report: dict[str, Any] = {
        "transaction_id": tid,
        "classification": score["classification"],
        "confidence": score["confidence"],
        "verdict_reason": score["verdict_reason"],
        "human_review_required": score["human_review_required"],

        # Document
        "doc_type": doc_type,
        "doc_type_confidence": round(doc_type_confidence, 3),
        "upload_filename": upload_filename,
        "preview_url": preview_url,

        # Extracted fields (from extraction service)
        "extraction": extracted_fields,

        # All confidence dimensions
        "confidence_scores": score.get("confidence_scores") or {},

        # Identity resolution
        "identity_resolution": identity,
        "barge_resolution": barge,

        # Fraud alerts (Phase 7)
        "fraud_alerts": fraud.get("fraud_alerts") or [],
        "info_alerts": fraud.get("info_alerts") or [],       # missing-evidence notices
        "overall_fraud_risk": fraud.get("overall_fraud_risk", "NONE"),
        "ais_evidence_status": score.get("ais_evidence_status", "unknown"),

        # Flags
        "credibility_flags": all_credibility_flags,
        "anomaly_flags": all_anomaly_flags,

        # Audit trail (Phase 8)
        "audit_trail": score.get("audit_trail") or [],

        # Evidence block
        "evidence": {
            "credibility_score": credibility.get("credibility_score"),
            "credibility_breakdown": credibility.get("breakdown"),
            "ocr_confidence": extracted_fields.get("ocr_confidence"),
            "extraction_confidence": extracted_fields.get("extraction_confidence"),
            "duplicate_detected": credibility.get("duplicate_detected", False),
            "duplicate_transaction_ids": credibility.get("duplicate_transaction_ids", []),
            **(ais.get("evidence") or {}),
        },

        # Meta
        "source": "orchestrator",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "document_processing": {
            "credibility_breakdown": credibility.get("breakdown"),
        },
    }

    return report
