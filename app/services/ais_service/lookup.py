"""Resolve confirmed IMO to MMSI and vessel metadata via the unified data provider."""

from __future__ import annotations

from typing import Any


def vessel_details(imo: str | None, mmsi: str | None = None) -> dict[str, Any] | None:
    """
    Returns vessel metadata dict or None.
    Routes through get_data_provider() so cached/live mode is respected by config.
    """
    if not imo or len(str(imo).strip()) != 7:
        return None
    from app.services.data_provider import get_data_provider
    return get_data_provider().get_vessel_by_imo(str(imo).strip())
