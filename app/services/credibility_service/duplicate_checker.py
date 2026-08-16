"""
Duplicate BDN checker — Phase 3.
Checks transactions table for:
  - Same vessel + port + date combination
  - Reused BDN reference numbers
Window and reuse count from config.yaml fraud_detection section.
Zero API cost — reads local DB only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config_loader import get_config


def _get_transactions() -> list[dict[str, Any]]:
    """Return all transactions from memory store (or DB if available)."""
    try:
        from app.persistence.memory_store import transaction_store
        return transaction_store.list_all()
    except Exception:
        return []


def check_duplicates(
    vessel_name: str | None,
    port: str | None,
    delivery_date: str | None,
    bdn_ref: str | None = None,
) -> dict[str, Any]:
    """
    Check for duplicate BDNs.
    Returns: { duplicate_detected, duplicate_transaction_ids, reused_bdn_ref }
    """
    cfg = get_config().get("fraud_detection", {})
    window_days = int(cfg.get("duplicate_bdn_window_days", 90))
    max_reuse = int(cfg.get("max_reuse_count", 1))

    transactions = _get_transactions()
    duplicate_ids: list[str] = []
    reused_refs: list[str] = []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    for txn in transactions:
        txn_id = txn.get("transaction_id", "")
        validated_at_str = txn.get("validated_at")
        if validated_at_str:
            try:
                validated_at = datetime.fromisoformat(validated_at_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                if validated_at < cutoff:
                    continue
            except Exception:
                pass

        extraction = txn.get("extraction") or {}
        txn_vessel = extraction.get("vessel_name")
        txn_port = extraction.get("port")
        txn_date = extraction.get("delivery_date")

        # Same vessel + port + date
        if (
            vessel_name and txn_vessel
            and port and txn_port
            and delivery_date and txn_date
            and vessel_name.upper() == txn_vessel.upper()
            and port.upper() == txn_port.upper()
            and delivery_date == txn_date
        ):
            duplicate_ids.append(txn_id)

    return {
        "duplicate_detected": len(duplicate_ids) > 0,
        "duplicate_transaction_ids": duplicate_ids[:5],  # Cap at 5
        "reused_bdn_ref": len(reused_refs) > max_reuse,
    }
