"""
Datalastic API client with graceful fallback to local registry.

When data_provider.mode == 'cached' in config.yaml, all live API calls are
skipped and lookups fall through directly to registry_fallback (the local JSON).
When mode == 'live', behaves as before — tries Datalastic first, then fallback.

This ensures zero network traffic in offline / trial-expired mode.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.config_loader import get_config
from app.services.identity_service import registry_fallback

_embedding_model = None


def _api_config() -> dict:
    return get_config()["api"]


def _api_key() -> str | None:
    return os.getenv("DATALASTIC_API_KEY")


def _is_cached_mode() -> bool:
    """Return True when the system is configured to run offline from disk cache."""
    return get_config().get("data_provider", {}).get("mode", "live").lower() == "cached"


def _request(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Live HTTP request. Skipped when cached mode is active."""
    if _is_cached_mode():
        return None

    api_key = _api_key()
    if not api_key:
        return None

    try:
        import httpx
        cfg = _api_config()
        base = cfg["datalastic_base_url"].rstrip("/")
        timeout = float(cfg["request_timeout_seconds"])
        params = {**params, "api-key": api_key}
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base}{path}", params=params)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def _normalize_vessel(raw: dict[str, Any], imo: str | None = None) -> dict[str, Any]:
    return {
        "imo": str(raw.get("imo") or imo or ""),
        "name": raw.get("name") or raw.get("ship_name") or "",
        "mmsi": str(raw.get("mmsi") or raw.get("mmsi_number") or "") or None,
        "vessel_type": raw.get("type") or raw.get("vessel_type"),
        "source": "datalastic" if not _is_cached_mode() else "cache",
    }


def get_vessel_by_imo(imo: str) -> dict[str, Any] | None:
    """
    Fetch vessel record by IMO.
    In cached mode: goes directly to registry_fallback (local JSON).
    In live mode: tries Datalastic API first, then registry_fallback.
    """
    if not _is_cached_mode():
        payload = _request("/vessel", {"imo": imo})
        if payload:
            data = payload.get("data") or payload.get("vessel") or payload
            if isinstance(data, list) and data:
                data = data[0]
            if isinstance(data, dict) and data.get("name"):
                return _normalize_vessel(data, imo)

    return registry_fallback.get_vessel_by_imo(imo)


def search_vessel_by_name(name: str) -> list[dict[str, Any]]:
    """
    Search vessels by name.
    In cached mode: goes directly to registry_fallback.
    In live mode: tries Datalastic API first, then registry_fallback.
    """
    if not _is_cached_mode():
        payload = _request("/vessel_find", {"name": name})
        results: list[dict[str, Any]] = []
        if payload:
            items = payload.get("data") or payload.get("vessels") or []
            if isinstance(items, dict):
                items = items.get("vessels") or items.get("data") or []
            for item in items[:5]:
                if isinstance(item, dict):
                    imo = str(item.get("imo") or "")
                    normalized = _normalize_vessel(item, imo)
                    if normalized.get("name"):
                        results.append(normalized)
        if results:
            return results

    return registry_fallback.search_vessel_by_name(name)


# Alias for backward compat
def find_vessel_by_name(name: str, type_specific: str | None = None) -> list[dict[str, Any]] | None:
    results = search_vessel_by_name(name)
    return results if results else None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    model_name = get_config()["identity"]["embedding_model"]
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _embedding_model = SentenceTransformer(model_name)
        return _embedding_model
    except Exception:
        return None
