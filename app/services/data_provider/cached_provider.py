"""
services/data_provider/cached_provider.py

Reads vessel and AIS data from disk cache (data/ais_cache/).
Produced by scripts/seed_cache.py — fully offline, no API calls.

Cache file naming convention (from seed_cache.py):
  vessel_imo_{imo}.json
  vessel_search_{slug}.json
  vessel_search_{slug}_tanker.json
  vessel_search_{slug}_any.json
  ais_history_{mmsi}_{date_from}_{date_to}.json    (date = YYYY-MM-DD)
  vessel_radius_{lat_str}_{lon_str}.json

AIS history JSON structure (top-level dict with "positions" array):
  {
    "mmsi": "...",
    "name": "...",
    "positions": [
      { "lat": 1.23, "lon": 103.84, "speed": 0.2,
        "heading": 90, "last_position_UTC": "2026-02-03T09:00:00Z" },
      ...
    ]
  }

Vessel JSON structure (flat dict):
  { "name": "STAR ELIZABETH", "mmsi": "636020763", "imo": "9917488",
    "country_iso": "LR", "type": "Cargo", "type_specific": "Bulk Carrier", ... }
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date as _date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    """Convert vessel/barge name to cache filename slug."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _normalize_vessel(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise cached vessel record to match datalastic_client output."""
    return {
        "imo":          str(raw.get("imo") or ""),
        "name":         raw.get("name") or raw.get("ship_name") or "",
        "mmsi":         str(raw.get("mmsi") or raw.get("mmsi_number") or "") or None,
        "flag":         raw.get("flag") or raw.get("country_iso"),
        "type":         raw.get("type"),
        "type_specific": raw.get("type_specific"),
        "source":       "cache",
    }


def _normalize_positions(raw_positions: list[dict]) -> list[dict[str, Any]]:
    """Convert cached positions to the format expected by ais_service/history.py."""
    from datetime import datetime, timezone
    result = []
    for p in raw_positions:
        try:
            lat = float(p.get("lat") or p.get("latitude") or 0)
            lon = float(p.get("lon") or p.get("longitude") or 0)
        except (TypeError, ValueError):
            continue

        ts_raw = (
            p.get("last_position_UTC")
            or p.get("timestamp")
            or p.get("last_position_utc")
            or p.get("time")
        )
        epoch = p.get("last_position_epoch")
        if ts_raw and isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        elif epoch:
            ts = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
        else:
            continue  # skip positions with no timestamp

        result.append({
            "lat":      lat,
            "lon":      lon,
            "speed":    float(p.get("speed") or p.get("sog") or 0),
            "heading":  float(p.get("heading") or p.get("course") or p.get("cog") or 0),
            "timestamp": ts,
        })
    result.sort(key=lambda x: x["timestamp"])
    return result


class CachedDataProvider:
    """
    Offline data provider. Reads from data/ais_cache/ directory.
    All public methods mirror the datalastic_client interface so
    the rest of the pipeline is unaffected.
    """

    def __init__(self, cache_dir: str | Path = "data/ais_cache") -> None:
        self._dir = Path(cache_dir)
        if not self._dir.exists():
            logger.warning("Cache dir '%s' not found — all lookups will return None", cache_dir)

    def _load(self, filename: str) -> dict | list | None:
        path = self._dir / filename
        if not path.exists():
            logger.debug("Cache miss: %s", filename)
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Cache read error %s: %s", filename, exc)
            return None

    # ── Vessel by IMO ──────────────────────────────────────────────────────────

    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        raw = self._load(f"vessel_imo_{imo}.json")
        if not raw:
            return None
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        return _normalize_vessel(raw) if raw else None

    # ── Vessel search by name ──────────────────────────────────────────────────

    def find_vessel_by_name(
        self, name: str, type_specific: str | None = None
    ) -> list[dict[str, Any]] | None:
        slug = _slug(name)
        suffix = f"_{type_specific}" if type_specific else ""

        # Try most specific file first, then fall back
        for fname in [
            f"vessel_search_{slug}{suffix}.json",
            f"vessel_search_{slug}_any.json",
            f"vessel_search_{slug}.json",
        ]:
            raw = self._load(fname)
            if raw is None:
                continue
            if isinstance(raw, dict):
                raw = [raw]
            return [_normalize_vessel(v) for v in raw if isinstance(v, dict)]

        return None

    # ── Vessels in radius ─────────────────────────────────────────────────────

    def get_vessels_in_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        type_specific: str | None = None,
        time: str | None = None,
    ) -> list[dict[str, Any]] | None:
        # Match cached file by rounding coords to 3dp (seed_cache rounds to 4dp)
        lat_str = str(round(lat, 4)).replace(".", "_")
        lon_str = str(round(lon, 4)).replace(".", "_")
        raw = self._load(f"vessel_radius_{lat_str}_{lon_str}.json")
        if raw is None:
            return None
        if isinstance(raw, dict):
            raw = [raw]
        return [_normalize_vessel(v) for v in raw if isinstance(v, dict)]

    # ── AIS history ────────────────────────────────────────────────────────────

    def get_ais_history(
        self, mmsi: str, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        """
        Return normalised position list for MMSI within date window.

        Strategy:
        1. Exact filename match → preferred.
        2. Scan all ais_history_{mmsi}_*.json files and pick first whose
           cached window fully contains or overlaps the requested window.
        """
        exact = self._load(f"ais_history_{mmsi}_{date_from}_{date_to}.json")
        if exact is not None:
            positions = exact.get("positions", []) if isinstance(exact, dict) else []
            return _normalize_positions(positions)

        # Fuzzy window match — find any cache file for this MMSI
        if not self._dir.exists():
            return []

        req_from = _date.fromisoformat(date_from)
        req_to   = _date.fromisoformat(date_to)
        prefix   = f"ais_history_{mmsi}_"

        best: list[dict] = []
        for path in sorted(self._dir.glob(f"{prefix}*.json")):
            # Extract dates from filename: ais_history_{mmsi}_{from}_{to}.json
            stem = path.stem  # e.g. ais_history_235090341_2026-02-10_2026-02-12
            parts = stem.split("_")
            # last two date segments
            try:
                cached_to   = _date.fromisoformat(parts[-1] + "-" + parts[-2] + "-" + parts[-3])
                cached_from = _date.fromisoformat(parts[-6] + "-" + parts[-5] + "-" + parts[-4])
            except (ValueError, IndexError):
                # filename date parsing failed — try simpler split
                try:
                    # stem = ais_history_{mmsi}_{YYYY}-{MM}-{DD}_{YYYY}-{MM}-{DD}
                    # After removing prefix: "{YYYY}-{MM}-{DD}_{YYYY}-{MM}-{DD}"
                    date_part = stem[len(prefix):]  # "2026-02-10_2026-02-12"
                    d_from_str, d_to_str = date_part.split("_", 1)
                    cached_from = _date.fromisoformat(d_from_str)
                    cached_to   = _date.fromisoformat(d_to_str)
                except Exception:
                    logger.debug("Cannot parse dates from filename: %s", path.name)
                    continue

            # Accept if cached window overlaps with requested window
            if cached_from <= req_to and cached_to >= req_from:
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    positions = data.get("positions", []) if isinstance(data, dict) else []
                    normed = _normalize_positions(positions)
                    if len(normed) > len(best):
                        best = normed  # prefer the file with most positions
                except Exception as exc:
                    logger.error("Cache read error %s: %s", path.name, exc)

        return best

    # ── Aliases for backward compat ────────────────────────────────────────────

    def search_vessel_by_name(self, name: str) -> list[dict[str, Any]]:
        return self.find_vessel_by_name(name) or []

    def vessel_details(self, imo: str | None, mmsi: str | None = None) -> dict[str, Any] | None:
        if imo:
            return self.get_vessel_by_imo(str(imo))
        return None
