"""
services/data_provider/stub_provider.py

Temporary stand-in for the Datalastic live API while the account is suspended.
Behaviour:
  1. Try the local cache (CachedDataProvider) first — real data wins.
  2. On any cache miss, return synthesised placeholder data so the pipeline
     can complete without errors.

Classifications produced while the stub is active will be REVIEW_REQUIRED
rather than HIGH_RISK, because vessel/barge identity will resolve to stub
records (low-but-nonzero confidence) and AIS tracks will be synthetic
(anomaly score close to zero, no distance/speed violations).

Remove this mode once the Datalastic account is renewed and set
data_provider.mode back to "live" in config.yaml.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.data_provider.cached_provider import CachedDataProvider

logger = logging.getLogger(__name__)

# Approximate coordinates for common bunkering hubs — used when we have no
# other location signal to anchor synthetic AIS tracks.
_FALLBACK_PORT_COORDS = (1.2655, 103.8200)  # Singapore / Johor Strait


def _seeded_random(seed_str: str) -> random.Random:
    """Return a deterministic Random instance for a given string seed."""
    digest = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    return random.Random(digest % (2**32))


def _stub_vessel(imo: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Build a minimal vessel dict that satisfies the pipeline's identity resolver."""
    rng = _seeded_random(str(imo or name or "unknown"))
    stub_imo = imo or f"999{rng.randint(1000, 9999)}"
    stub_mmsi = f"6{rng.randint(10000000, 99999999)}"
    stub_name = name or f"STUB VESSEL {stub_imo}"
    return {
        "imo": stub_imo,
        "name": stub_name.upper(),
        "mmsi": stub_mmsi,
        "flag": "XX",
        "type": "Cargo",
        "type_specific": "Tanker",
        "source": "stub",
    }


def _stub_ais_track(
    mmsi: str,
    date_from: str,
    date_to: str,
    lat: float | None = None,
    lon: float | None = None,
) -> list[dict[str, Any]]:
    """
    Generate a synthetic AIS track for the requested MMSI and date window.

    The vessel is placed at a fixed anchorage position (very low speed, small
    random drift) to mimic a vessel moored during bunkering. This keeps the
    ML feature vector well within the normal range and avoids spurious
    HIGH_RISK classifications while the stub is active.
    """
    rng = _seeded_random(f"{mmsi}_{date_from}_{date_to}")

    base_lat = lat if lat is not None else _FALLBACK_PORT_COORDS[0]
    base_lon = lon if lon is not None else _FALLBACK_PORT_COORDS[1]

    # Small random offset per MMSI so vessel and barge don't overlap exactly
    base_lat += rng.uniform(-0.002, 0.002)
    base_lon += rng.uniform(-0.002, 0.002)

    try:
        t_start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        t_end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
    except ValueError:
        t_start = datetime.now(tz=timezone.utc) - timedelta(days=1)
        t_end = datetime.now(tz=timezone.utc)

    interval_minutes = 10
    positions: list[dict[str, Any]] = []
    current = t_start
    while current <= t_end:
        # Drift stays within ~50 m — typical for an anchored vessel
        lat_jitter = rng.gauss(0, 0.0002)
        lon_jitter = rng.gauss(0, 0.0002)
        positions.append({
            "lat": round(base_lat + lat_jitter, 6),
            "lon": round(base_lon + lon_jitter, 6),
            "speed": round(abs(rng.gauss(0.2, 0.15)), 2),
            "heading": float(rng.randint(0, 359)),
            "timestamp": current,
        })
        current += timedelta(minutes=interval_minutes)

    logger.info(
        "StubProvider: synthesised %d AIS positions for MMSI %s (%s→%s)",
        len(positions), mmsi, date_from, date_to,
    )
    return positions


class StubDataProvider:
    """
    Cache-first provider with synthetic fallback for every call type.
    Used when data_provider.mode = "stub".
    """

    def __init__(self, cache_dir: str = "data/ais_cache") -> None:
        self._cache = CachedDataProvider(cache_dir=cache_dir)

    # ── Vessel by IMO ──────────────────────────────────────────────────────────

    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        result = self._cache.get_vessel_by_imo(imo)
        if result:
            return result
        logger.debug("StubProvider: cache miss for IMO %s — returning stub vessel", imo)
        return _stub_vessel(imo=imo)

    # ── Vessel search by name ──────────────────────────────────────────────────

    def find_vessel_by_name(
        self, name: str, type_specific: str | None = None
    ) -> list[dict[str, Any]] | None:
        result = self._cache.find_vessel_by_name(name, type_specific=type_specific)
        if result:
            return result
        logger.debug("StubProvider: cache miss for name '%s' — returning stub vessel", name)
        return [_stub_vessel(name=name)]

    def search_vessel_by_name(self, name: str) -> list[dict[str, Any]]:
        return self.find_vessel_by_name(name) or []

    # ── Vessels in radius ─────────────────────────────────────────────────────

    def get_vessels_in_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        type_specific: str | None = None,
        time: str | None = None,
    ) -> list[dict[str, Any]] | None:
        result = self._cache.get_vessels_in_radius(lat, lon, radius_km, type_specific, time)
        if result:
            return result
        logger.debug("StubProvider: no radius cache at (%.4f, %.4f) — returning stub barge", lat, lon)
        rng = _seeded_random(f"{round(lat,3)}_{round(lon,3)}")
        stub = _stub_vessel(name=f"STUB BARGE {rng.randint(100, 999)}")
        stub["type_specific"] = "Barge"
        return [stub]

    # ── AIS history ────────────────────────────────────────────────────────────

    def get_ais_history(
        self, mmsi: str, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        result = self._cache.get_ais_history(mmsi, date_from, date_to)
        if result:
            return result
        logger.debug(
            "StubProvider: no AIS cache for MMSI %s (%s→%s) — generating synthetic track",
            mmsi, date_from, date_to,
        )
        return _stub_ais_track(mmsi, date_from, date_to)

    # ── Vessel details ────────────────────────────────────────────────────────

    def vessel_details(self, imo: str | None, mmsi: str | None = None) -> dict[str, Any] | None:
        result = self._cache.vessel_details(imo, mmsi)
        if result:
            return result
        if imo:
            return _stub_vessel(imo=str(imo))
        return None
