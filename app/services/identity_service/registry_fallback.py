"""
Local vessel registry used when Datalastic is unavailable (dev/demo).
"""

from __future__ import annotations

from typing import Any

# IMO -> vessel record
REGISTRY: dict[str, dict[str, str]] = {
    "9876543": {"name": "STAR PHOENIX TANKER", "mmsi": "538009999", "vessel_type": "Tanker"},
    "1234567": {"name": "OCEAN STAR", "mmsi": "538001234", "vessel_type": "Bulk Carrier"},
    "7654321": {"name": "OCEAN STAR TRADER", "mmsi": "538005678", "vessel_type": "Bulk Carrier"},
}

# Normalized name -> IMO (reverse lookup)
_NAME_INDEX: dict[str, str] | None = None


def _name_key(name: str) -> str:
    return "".join(ch for ch in name.upper() if ch.isalnum())


def _build_name_index() -> dict[str, str]:
    global _NAME_INDEX
    if _NAME_INDEX is not None:
        return _NAME_INDEX
    _NAME_INDEX = {_name_key(rec["name"]): imo for imo, rec in REGISTRY.items()}
    return _NAME_INDEX


def get_vessel_by_imo(imo: str) -> dict[str, Any] | None:
    rec = REGISTRY.get(imo)
    if not rec:
        return None
    return {"imo": imo, **rec, "source": "local_registry"}


def search_vessel_by_name(name: str) -> list[dict[str, Any]]:
    key = _name_key(name)
    index = _build_name_index()
    results: list[dict[str, Any]] = []

    if key in index:
        imo = index[key]
        results.append(get_vessel_by_imo(imo))

    for imo, rec in REGISTRY.items():
        rec_key = _name_key(rec["name"])
        if key in rec_key or rec_key in key:
            vessel = get_vessel_by_imo(imo)
            if vessel and vessel not in results:
                results.append(vessel)

    return results
