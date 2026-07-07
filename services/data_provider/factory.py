"""
services/data_provider/factory.py

Returns the appropriate data provider based on config.yaml data_provider.mode.

  mode: cached  → CachedDataProvider  (reads from data/ais_cache/, fully offline)
  mode: live    → datalastic_client   (live API, requires DATALASTIC_API_KEY)

Usage anywhere in the pipeline:
    from services.data_provider import get_data_provider
    p = get_data_provider()
    vessel = p.get_vessel_by_imo("9917488")
    positions = p.get_ais_history("636020763", "2026-02-03", "2026-02-03")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.data_provider.cached_provider import CachedDataProvider

_instance = None


def get_data_provider():
    """
    Return cached singleton provider instance.
    Thread-safe for read-only use (no locking needed — config doesn't change
    between requests in normal operation).
    """
    global _instance
    if _instance is not None:
        return _instance

    from core.config_loader import get_config
    cfg = get_config().get("data_provider", {})
    mode = cfg.get("mode", "live").lower()

    if mode == "cached":
        from services.data_provider.cached_provider import CachedDataProvider
        cache_dir = cfg.get("cache_dir", "data/ais_cache")
        _instance = CachedDataProvider(cache_dir=cache_dir)
    elif mode == "stub":
        from services.data_provider.stub_provider import StubDataProvider
        cache_dir = cfg.get("cache_dir", "data/ais_cache")
        _instance = StubDataProvider(cache_dir=cache_dir)
    else:
        # Live mode: return a thin wrapper around the existing datalastic_client
        from services.data_provider.live_provider import LiveDataProvider
        _instance = LiveDataProvider()

    return _instance


def reset_provider() -> None:
    """Force re-instantiation on next call (useful after config reload)."""
    global _instance
    _instance = None
