"""
services/data_provider/live_provider.py

Thin wrapper around the existing datalastic_client so it satisfies
the same interface as CachedDataProvider.
"""

from __future__ import annotations

from typing import Any

from services.vessel_verification_service import datalastic_client


class LiveDataProvider:
    """Delegates all calls to the centralised Datalastic API client."""

    def get_vessel_by_imo(self, imo: str) -> dict[str, Any] | None:
        return datalastic_client.get_vessel_by_imo(imo)

    def find_vessel_by_name(
        self, name: str, type_specific: str | None = None
    ) -> list[dict[str, Any]] | None:
        return datalastic_client.find_vessel_by_name(name, type_specific=type_specific)

    def get_vessels_in_radius(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        type_specific: str | None = None,
        time: str | None = None,
    ) -> list[dict[str, Any]] | None:
        return datalastic_client.get_vessels_in_radius(
            lat, lon, radius_km, type_specific=type_specific, time=time
        )

    def get_ais_history(
        self, mmsi: str, date_from: str, date_to: str
    ) -> list[dict[str, Any]]:
        result = datalastic_client.get_vessel_history(mmsi, date_from, date_to)
        return result or []

    def search_vessel_by_name(self, name: str) -> list[dict[str, Any]]:
        return datalastic_client.search_vessel_by_name(name)

    def vessel_details(self, imo: str | None, mmsi: str | None = None) -> dict[str, Any] | None:
        return datalastic_client.vessel_details(imo, mmsi)
