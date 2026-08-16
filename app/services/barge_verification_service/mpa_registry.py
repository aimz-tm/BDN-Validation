"""
MPA barge registry loader and fuzzy searcher — Phase 5.
Reads data/mpa_barge_registry.json.
Path configurable in config.yaml.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz  # type: ignore
except ImportError:
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def token_sort_ratio(a: str, b: str) -> float:
            a_s = " ".join(sorted(a.split()))
            b_s = " ".join(sorted(b.split()))
            return SequenceMatcher(None, a_s, b_s).ratio() * 100.0

    fuzz = _FuzzFallback()  # type: ignore

from app.core.config_loader import get_config

logger = logging.getLogger(__name__)

_registry_cache: list[dict[str, Any]] | None = None


def _load_registry() -> list[dict[str, Any]]:
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    cfg = get_config().get("barge_verification", {})
    registry_path = Path(cfg.get("mpa_registry_path", "data/mpa_barge_registry.json"))

    if not registry_path.exists():
        logger.warning("MPA registry not found at %s — creating empty stub", registry_path)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("[]", encoding="utf-8")

    try:
        _registry_cache = json.loads(registry_path.read_text(encoding="utf-8"))
        return _registry_cache
    except Exception as exc:
        logger.error("Failed to load MPA registry: %s", exc)
        _registry_cache = []
        return _registry_cache


def _normalize_name(name: str) -> str:
    """Remove common prefixes, spaces, hyphens; uppercase."""
    if not name:
        return ""
    cfg = get_config().get("barge_verification", {})
    prefixes = cfg.get("name_prefixes_to_strip", ["MT ", "MV ", "M/V ", "M/T "])
    n = name.strip().upper()
    for pfx in prefixes:
        if n.startswith(pfx.upper()):
            n = n[len(pfx):]
            break
    return n.replace(" ", "").replace("-", "")


def search_by_name(barge_name: str, threshold: float = 75.0) -> list[dict[str, Any]]:
    """
    Fuzzy search registry by barge name.
    Also checks normalized (no-space, no-prefix) forms for alias matching.
    """
    registry = _load_registry()
    if not registry:
        return []

    query_norm = _normalize_name(barge_name)
    query = barge_name.strip().upper()
    results: list[tuple[float, dict[str, Any]]] = []

    for entry in registry:
        reg_name = (entry.get("name") or "").upper()
        reg_norm = _normalize_name(reg_name)

        # Standard fuzzy
        score = fuzz.token_sort_ratio(query, reg_name)
        # Normalized alias match
        if query_norm and reg_norm:
            norm_score = fuzz.token_sort_ratio(query_norm, reg_norm)
            score = max(score, norm_score)

        if score >= threshold:
            results.append((score, {**entry, "_match_score": round(score, 1)}))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:5]]


def search_by_sb(sb_number: str) -> dict[str, Any] | None:
    """Look up barge by SB number."""
    registry = _load_registry()
    sb_upper = sb_number.strip().upper()
    for entry in registry:
        if (entry.get("sb_number") or "").upper() == sb_upper:
            return entry
    return None
