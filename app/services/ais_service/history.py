"""
Fetch historical AIS positions with graceful failure.

Routes through the unified data provider (cached or live per config.yaml):
  data_provider.mode = cached  →  reads data/ais_cache/*.json files, no network calls
  data_provider.mode = live    →  calls Datalastic API (requires DATALASTIC_API_KEY)

Switching between modes is a config-only change — no code changes needed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config_loader import get_config
from app.services.ais_service import cache


def fetch_positions(
    mmsi: str,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Returns (positions, error). error is None on success.

    Uses in-memory session cache to avoid re-reading disk on the same request.
    Then delegates to get_data_provider() for the actual data source.
    """
    start_iso = start_utc.strftime("%Y-%m-%d")
    end_iso = end_utc.strftime("%Y-%m-%d")

    # Check in-memory session cache first
    session_cached = cache.get(mmsi, start_iso, end_iso)
    if session_cached is not None:
        return session_cached, None

    from app.services.data_provider import get_data_provider
    provider = get_data_provider()

    try:
        positions = provider.get_ais_history(mmsi, start_iso, end_iso)
    except Exception as exc:
        return [], str(exc)

    if positions:
        cache.set(mmsi, start_iso, end_iso, positions)
        return positions, None

    # No positions found — give a mode-specific error message for logging clarity
    mode = get_config().get("data_provider", {}).get("mode", "live").lower()
    if mode == "cached":
        return [], f"no_cached_ais_data_for_mmsi_{mmsi}_{start_iso}_{end_iso}"
    return [], "ais_fetch_returned_empty"
