"""
Barge verification resolver — Phase 5.
Full resolution chain (FLAG_010 + FLAG_011):
Step 0: Historical transaction match (DB, zero API cost)
Step 1: SB + name cross-validation (MPA registry)
Step 2: Datalastic vessel_find + type filter
Step 3: vessel_inradius fallback
Step 4: Unresolved → barge_ais_missing: true (FLAG_002)

Barge ONLY identified by name — no IMO check.
"""

from __future__ import annotations

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

from core.config_loader import get_config
from services.barge_verification_service import mpa_registry
from services.vessel_verification_service import datalastic_client


def _historical_match(barge_name: str) -> dict[str, Any] | None:
    """Step 0: Check past transactions for known barge name."""
    try:
        from persistence.memory_store import transaction_store
        for txn in transaction_store.list_all():
            ext = txn.get("extraction") or {}
            past_name = ext.get("barge_name")
            if not past_name:
                continue
            score = fuzz.token_sort_ratio(barge_name.upper(), past_name.upper())
            if score >= 85.0:
                identity = txn.get("identity_resolution") or {}
                barge_res = txn.get("barge_resolution") or {}
                if barge_res.get("barge_confirmed_name"):
                    return {
                        "barge_confirmed_name": barge_res["barge_confirmed_name"],
                        "barge_mmsi": barge_res.get("barge_mmsi"),
                        "resolution_method": "historical_match",
                        "barge_confidence": round(score / 100, 3),
                        "resolution_evidence": {"source": "transaction_history", "match_score": score, "txn_id": txn.get("transaction_id")},
                    }
    except Exception:
        pass
    return None


def resolve_barge_identity(
    barge_name: str | None,
    sb_number: str | None = None,
    vessel_lat: float | None = None,
    vessel_lon: float | None = None,
    delivery_start: Any = None,
    delivery_end: Any = None,
) -> dict[str, Any]:
    """
    Resolve barge identity. Returns full barge verification result.
    """
    result: dict[str, Any] = {
        "barge_confirmed_name": None,
        "barge_mmsi": None,
        "barge_imo": None,
        "resolution_method": "unresolved",
        "barge_confidence": 0.0,
        "barge_flags": [],
        "barge_ais_missing": True,
        "resolution_evidence": {},
    }

    if not barge_name:
        result["barge_flags"].append("barge_name_missing")
        return result

    # Step 0: Historical transaction match
    hist = _historical_match(barge_name)
    if hist:
        result.update(hist)
        result["barge_ais_missing"] = not hist.get("barge_mmsi")
        return result

    # Step 1: MPA registry — SB + name cross-validation
    cfg = get_config().get("barge_verification", {})
    registry_threshold = float(cfg.get("registry_fuzzy_threshold", 75.0))

    if sb_number:
        sb_match = mpa_registry.search_by_sb(sb_number)
        if sb_match:
            reg_name = sb_match.get("name", "")
            name_score = fuzz.token_sort_ratio(barge_name.upper(), reg_name.upper())
            if name_score >= 60.0:  # Loose — SB already confirms
                result.update({
                    "barge_confirmed_name": reg_name or barge_name,
                    "barge_mmsi": sb_match.get("mmsi"),
                    "barge_imo": sb_match.get("imo"),
                    "resolution_method": "mpa_registry_sb",
                    "barge_confidence": round(max(name_score / 100, 0.80), 3),
                    "barge_ais_missing": not sb_match.get("mmsi"),
                    "resolution_evidence": {"source": "mpa_registry", "sb_number": sb_number, "match_score": name_score},
                })
                return result

    name_matches = mpa_registry.search_by_name(barge_name, threshold=registry_threshold)
    if name_matches:
        best = name_matches[0]
        result.update({
            "barge_confirmed_name": best.get("name") or barge_name,
            "barge_mmsi": best.get("mmsi"),
            "barge_imo": best.get("imo"),
            "resolution_method": "mpa_registry_name",
            "barge_confidence": round(best.get("_match_score", 75) / 100, 3),
            "barge_ais_missing": not best.get("mmsi"),
            "resolution_evidence": {"source": "mpa_registry_name", "match_score": best.get("_match_score")},
        })
        return result

    # Step 2: Datalastic vessel_find — tanker-specific first, then generic fallback
    # Only make generic call if tanker search returned nothing at all (not just no match)
    datalastic_results = datalastic_client.find_vessel_by_name(barge_name, type_specific="tanker") or []
    if not datalastic_results:
        # tanker search returned empty — try generic (bunker barges may be typed differently)
        datalastic_results = datalastic_client.find_vessel_by_name(barge_name) or []


    if datalastic_results:
        best = datalastic_results[0]
        api_name = best.get("name", "")
        score = fuzz.token_sort_ratio(barge_name.upper(), api_name.upper()) / 100.0
        if score >= 0.70:
            result.update({
                "barge_confirmed_name": api_name or barge_name,
                "barge_mmsi": best.get("mmsi"),
                "barge_imo": best.get("imo"),
                "resolution_method": "datalastic_name",
                "barge_confidence": round(score, 3),
                "barge_ais_missing": not best.get("mmsi"),
                "resolution_evidence": {"source": "datalastic", "api_name": api_name, "match_score": round(score, 3)},
            })
            return result

    # Step 3: vessel_inradius fallback
    if vessel_lat is not None and vessel_lon is not None:
        radius_results = datalastic_client.get_vessels_in_radius(
            vessel_lat, vessel_lon, radius_km=5.0, type_specific="tanker"
        ) or []
        for vessel in radius_results:
            api_name = vessel.get("name", "")
            score = fuzz.token_sort_ratio(barge_name.upper(), api_name.upper()) / 100.0
            if score >= 0.70:
                result.update({
                    "barge_confirmed_name": api_name or barge_name,
                    "barge_mmsi": vessel.get("mmsi"),
                    "barge_imo": vessel.get("imo"),
                    "resolution_method": "inradius_fallback",
                    "barge_confidence": round(score, 3),
                    "barge_ais_missing": False,
                    "resolution_evidence": {"source": "inradius", "match_score": round(score, 3)},
                })
                return result

    # Step 4: Unresolved
    result["barge_flags"].append("barge_ais_missing")
    result["barge_confirmed_name"] = barge_name  # Use BDN name as-is
    return result
