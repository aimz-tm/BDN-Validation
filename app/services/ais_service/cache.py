"""In-memory AIS history cache."""

from __future__ import annotations

from typing import Any

_cache: dict[str, list[dict[str, Any]]] = {}


def _key(mmsi: str, start_iso: str, end_iso: str) -> str:
    return f"{mmsi}|{start_iso}|{end_iso}"


def get(mmsi: str, start_iso: str, end_iso: str) -> list[dict[str, Any]] | None:
    return _cache.get(_key(mmsi, start_iso, end_iso))


def set(mmsi: str, start_iso: str, end_iso: str, positions: list[dict[str, Any]]) -> None:
    _cache[_key(mmsi, start_iso, end_iso)] = positions
