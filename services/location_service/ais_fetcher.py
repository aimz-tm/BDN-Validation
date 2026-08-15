"""
AIS fetcher — Phase 6.
Wraps DatalasticClient for vessel + barge AIS track fetching.
Handles missing barge gracefully (FLAG_002). Caches results per session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.vessel_verification_service.datalastic_client import get_vessel_history

_session_cache: dict[str, Any] = {}


def _cache_key(mmsi: str, start: datetime, end: datetime) -> str:
    return f"{mmsi}_{start.isoformat()}_{end.isoformat()}"


def fetch_vessel_positions(
    mmsi: str,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Fetch vessel AIS positions. Returns (positions, error_string | None).
    Caches per session.
    """
    key = _cache_key(mmsi, start_utc, end_utc)
    if key in _session_cache:
        return _session_cache[key], None

    date_from = start_utc.strftime("%Y-%m-%d %H:%M:%S")
    date_to = end_utc.strftime("%Y-%m-%d %H:%M:%S")

    try:
        raw = get_vessel_history(mmsi, date_from, date_to)
        if not raw:
            return [], "No AIS history returned"
        positions = _normalize_positions(raw)
        _session_cache[key] = positions
        return positions, None
    except Exception as exc:
        return [], str(exc)


def fetch_barge_positions(
    barge_mmsi: str | None,
    start_utc: datetime,
    end_utc: datetime,
) -> list[dict[str, Any]] | None:
    """
    Fetch barge positions. Returns None if barge MMSI unavailable (FLAG_002).
    """
    if not barge_mmsi:
        return None  # FLAG_002: barge AIS missing

    positions, error = fetch_vessel_positions(barge_mmsi, start_utc, end_utc)
    if error:
        return None
    return positions


def _normalize_positions(raw: list[dict]) -> list[dict[str, Any]]:
    """Normalize Datalastic position records to standard format."""
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            lat = float(item.get("lat") or item.get("latitude") or 0)
            lon = float(item.get("lon") or item.get("longitude") or 0)
            speed = float(item.get("speed") or item.get("sog") or 0)
            heading = float(item.get("heading") or item.get("cog") or 0)
            ts_raw = item.get("timestamp") or item.get("time_utc") or ""
            ts = None
            if ts_raw:
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    pass
            out.append({"lat": lat, "lon": lon, "speed": speed, "heading": heading, "timestamp": ts})
        except Exception:
            continue
    return out
