"""
Centralised Datalastic API client — Phase 4.
Used by ALL verification services.
All endpoints, timeouts, retry, rate limiting here.
API key from config. Graceful failure: returns None + logs, never raises.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

import requests

from core.config_loader import get_config

logger = logging.getLogger(__name__)

_embedding_model_cache: Any = None

# Rolling-window token bucket — stores timestamps of recent calls
_request_timestamps: deque = deque()

# In-process response cache: (endpoint, frozenset(params)) → response
_response_cache: dict[tuple, Any] = {}


def _api_key() -> str | None:
    import os
    return os.getenv("DATALASTIC_API_KEY") or get_config().get("api", {}).get("datalastic_api_key")


def _base_url() -> str:
    return get_config().get("api", {}).get("datalastic_base_url", "https://api.datalastic.com/api/v0")


def _timeout() -> int:
    return int(get_config().get("api", {}).get("request_timeout_seconds", 10))


def _rate_limit() -> None:
    """
    Token-bucket rate limiter.
    Only sleeps when the rolling-hour quota is truly exhausted.
    Does NOT sleep between normal calls — previous impl slept 36s every call.
    """
    rate_limit = int(get_config().get("api", {}).get("rate_limit_per_hour", 100))
    window = 3600.0
    now = time.time()

    # Drop timestamps outside the 1-hour window
    while _request_timestamps and now - _request_timestamps[0] > window:
        _request_timestamps.popleft()

    if len(_request_timestamps) >= rate_limit:
        # Quota exhausted — wait until oldest request drops out of window
        sleep_for = window - (now - _request_timestamps[0]) + 0.05
        if sleep_for > 0:
            logger.warning("Datalastic rate limit reached — sleeping %.1fs", sleep_for)
            time.sleep(sleep_for)

    _request_timestamps.append(time.time())


def _verify_ssl() -> bool:
    return bool(get_config().get("api", {}).get("verify_ssl", True))


def _get(endpoint: str, params: dict) -> dict | list | None:
    """Internal GET with in-process caching and error handling."""
    key = _api_key()
    if not key:
        logger.warning("Datalastic API key not set — skipping call to %s", endpoint)
        return None

    # Cache lookup (excludes api-key from cache key)
    cache_key = (endpoint, frozenset((k, str(v)) for k, v in params.items()))
    if cache_key in _response_cache:
        logger.debug("Datalastic cache hit: %s %s", endpoint, params)
        return _response_cache[cache_key]

    _rate_limit()
    try:
        req_params = dict(params)
        req_params["api-key"] = key
        url = f"{_base_url()}/{endpoint}"
        resp = requests.get(url, params=req_params, timeout=_timeout(), verify=_verify_ssl())
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("data", data)
            _response_cache[cache_key] = result  # Cache successful responses
            return result
        logger.warning("Datalastic %s returned %s: %s", endpoint, resp.status_code, resp.text[:200])
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("Datalastic request failed for %s: %s", endpoint, exc)
        return None



def get_vessel_by_imo(imo: str) -> dict[str, Any] | None:
    """Fetch vessel record by IMO number."""
    result = _get("vessel", {"imo": imo})
    if isinstance(result, list):
        return result[0] if result else None
    return result if isinstance(result, dict) else None


def find_vessel_by_name(name: str, type_specific: str | None = None) -> list[dict[str, Any]] | None:
    """Search for vessels matching a name."""
    params: dict = {"name": name}
    if type_specific:
        params["type_specific"] = type_specific
    result = _get("vessel_find", params)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return None


def get_vessel_history(mmsi: str, date_from: str, date_to: str) -> list[dict[str, Any]] | None:
    """Fetch AIS position history for a vessel MMSI."""
    result = _get("vessel_history", {"mmsi": mmsi, "date_from": date_from, "date_to": date_to})
    if isinstance(result, list):
        return result
    return None


def get_vessels_in_radius(
    lat: float, lon: float, radius_km: float,
    type_specific: str | None = None,
    time: str | None = None,
) -> list[dict[str, Any]] | None:
    """Find vessels within radius of a coordinate."""
    params: dict = {"lat": lat, "lon": lon, "radius": radius_km}
    if type_specific:
        params["type_specific"] = type_specific
    if time:
        params["time"] = time
    result = _get("vessel_inradius", params)
    if isinstance(result, list):
        return result
    return None


# Keep backward compatibility (old identity_service used these)
def get_embedding_model() -> Any:
    """Load and cache sentence-transformers model."""
    global _embedding_model_cache
    if _embedding_model_cache is not None:
        return _embedding_model_cache
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        cfg = get_config().get("identity", {})
        model_name = cfg.get("embedding_model", "all-MiniLM-L6-v2")
        _embedding_model_cache = SentenceTransformer(model_name)
        return _embedding_model_cache
    except Exception as exc:
        logger.warning("Could not load embedding model: %s", exc)
        return None


# Aliases for backward compat with identity_service.datalastic_client
def search_vessel_by_name(name: str) -> list[dict[str, Any]]:
    return find_vessel_by_name(name) or []


def vessel_details(imo: str | None, mmsi: str | None = None) -> dict[str, Any] | None:
    if imo:
        return get_vessel_by_imo(imo)
    return None
