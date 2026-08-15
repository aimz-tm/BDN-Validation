from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from db.session import SessionLocal
from models.database import Transaction, Vessel
from services.timezone_service.converter import delivery_window_utc

# Classifications that mean a transaction has already been actioned by a
# reviewer (or auto-classified as clean) — it should never reappear in the
# review queue even if the stale human_review_required flag inside the
# validation_result JSON blob was never flipped back to False.
_ALREADY_REVIEWED_CLASSIFICATIONS = {"VALID", "REJECTED", "MANUALLY_APPROVED"}


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _upsert_vessel(
    db,
    *,
    imo: str | None,
    name: str | None,
    mmsi: str | None,
    vessel_type: str | None = None,
) -> Vessel | None:
    if not imo or len(str(imo)) != 7:
        return None
    vessel = db.scalar(select(Vessel).where(Vessel.imo == str(imo)))
    if vessel is None:
        if not name:
            return None
        vessel = Vessel(imo=str(imo), name=name, mmsi=mmsi, vessel_type=vessel_type)
        db.add(vessel)
    else:
        if name:
            vessel.name = name
        if mmsi:
            vessel.mmsi = mmsi
        if vessel_type:
            vessel.vessel_type = vessel_type
    return vessel


def persist_verdict(verdict: dict[str, Any]) -> bool:
    """
    Save validation result to DB. Returns False if DB unavailable or vessel unresolved.
    """
    extraction = verdict.get("extraction") or {}
    identity = verdict.get("identity_resolution") or {}
    barge_resolution = verdict.get("barge_resolution") or {}
    evidence = verdict.get("evidence") or {}
    window = delivery_window_utc(extraction)

    vessel_imo = identity.get("confirmed_imo") or extraction.get("imo")
    vessel_name = identity.get("confirmed_name") or extraction.get("vessel_name")
    vessel_mmsi = identity.get("confirmed_mmsi")
    barge_name = barge_resolution.get("barge_confirmed_name") or extraction.get("barge_name")
    barge_mmsi = barge_resolution.get("barge_mmsi")
    # Barges don't have IMO numbers — use None
    barge_imo = None

    try:
        with SessionLocal() as db:
            vessel = _upsert_vessel(
                db,
                imo=vessel_imo,
                name=vessel_name,
                mmsi=vessel_mmsi,
            )
            if vessel is None:
                db.rollback()
                return False

            barge = _upsert_vessel(
                db,
                imo=barge_imo,   # Always None — barges have no IMO
                name=barge_name,
                mmsi=barge_mmsi,
            )

            tx = Transaction(
                transaction_reference=verdict.get("transaction_id"),
                vessel=vessel,
                barge=barge,
                bdn_number=verdict.get("transaction_id"),
                delivery_start_at=window.get("start_utc"),
                delivery_end_at=window.get("end_utc"),
                port=extraction.get("port"),
                quantity_mt=_to_float(extraction.get("quantity_mt")),
                density=_to_float(extraction.get("density")),
                sulphur_content=_to_float(extraction.get("sulphur_content")),
                flashpoint=_to_float(extraction.get("flashpoint")),
                supplier=extraction.get("supplier"),
                classification=verdict.get("classification"),
                confidence=_to_float(verdict.get("confidence")),
                credibility_score=_to_float(evidence.get("credibility_score")),
                extracted_fields=extraction,
                validation_result=verdict,
                verdict_reason=verdict.get("verdict_reason"),
            )
            db.add(tx)
            db.commit()
            return True
    except SQLAlchemyError:
        return False


def list_transactions_db(
    *,
    human_review_only: bool = False,
    classification: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    try:
        with SessionLocal() as db:
            q = select(Transaction).order_by(desc(Transaction.created_at)).limit(limit)
            if classification:
                q = q.where(Transaction.classification == classification)
            rows = db.scalars(q).all()
            out: list[dict[str, Any]] = []
            for tx in rows:
                payload = tx.validation_result or {}
                if human_review_only and (
                    not payload.get("human_review_required", False)
                    or tx.classification in _ALREADY_REVIEWED_CLASSIFICATIONS
                ):
                    continue
                out.append(
                    {
                        "transaction_id": payload.get("transaction_id") or tx.transaction_reference or str(tx.id),
                        "classification": tx.classification,
                        "confidence": _to_float(tx.confidence) or 0.0,
                        "human_review_required": bool(payload.get("human_review_required", False)),
                        "validated_at": payload.get("validated_at") or tx.created_at.isoformat(),
                        "upload_filename": payload.get("upload_filename"),
                        "vessel_name": (payload.get("extraction") or {}).get("vessel_name") or (tx.vessel.name if tx.vessel else None),
                        "imo": (payload.get("identity_resolution") or {}).get("confirmed_imo") or (tx.vessel.imo if tx.vessel else None),
                        "port": (payload.get("extraction") or {}).get("port") or tx.port,
                        "verdict_reason": payload.get("verdict_reason") or tx.verdict_reason,
                        "barge_missing": bool(payload.get("barge_missing", False)),
                    }
                )
            return out
    except SQLAlchemyError:
        return []


def get_transaction_db(transaction_id: str) -> dict[str, Any] | None:
    try:
        with SessionLocal() as db:
            tx = db.scalar(
                select(Transaction).where(Transaction.transaction_reference == transaction_id)
            )
            if tx is None:
                return None
            if tx.validation_result:
                return tx.validation_result
            return {
                "transaction_id": transaction_id,
                "classification": tx.classification,
                "confidence": _to_float(tx.confidence) or 0.0,
                "verdict_reason": tx.verdict_reason,
                "extraction": tx.extracted_fields or {},
            }
    except SQLAlchemyError:
        return None
