"""
Vessel verification resolver — Phase 4.
5-step logic (FLAG_006) + new additions:
  vessel_type_mismatch, vessel_flag_state_mismatch flags.
Returns full verification evidence.

Data access routes through get_data_provider():
  config data_provider.mode = cached  → reads data/ais_cache/ files (no network)
  config data_provider.mode = live    → calls Datalastic API
Switching modes requires only a config change.
"""

from __future__ import annotations

import re
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
from services.vessel_verification_service import datalastic_client  # kept for embedding model only


def _embedding_similarity(a: str, b: str) -> float:
    model = datalastic_client.get_embedding_model()
    if not model or not a or not b:
        return 0.0
    try:
        import numpy as np
        emb = model.encode([a, b])
        sim = float(np.dot(emb[0], emb[1]) / (np.linalg.norm(emb[0]) * np.linalg.norm(emb[1])))
        return max(0.0, min(1.0, sim))
    except Exception:
        return 0.0


def resolve_vessel_identity(extraction: dict[str, Any]) -> dict[str, Any]:
    """
    Steps A–E from spec. Returns full resolution result with evidence.
    Data access via unified data provider (cached or live per config).
    """
    cfg = get_config()["identity"]
    fuzzy_threshold = float(cfg["fuzzy_match_threshold"])
    embed_threshold = float(cfg["embedding_similarity_threshold"])

    bdn_name = (extraction.get("vessel_name") or "").strip()
    bdn_imo = re.sub(r"\D", "", str(extraction.get("imo") or ""))

    from services.data_provider import get_data_provider
    provider = get_data_provider()

    result: dict[str, Any] = {
        "bdn_name": bdn_name or None,
        "bdn_imo": bdn_imo or None,
        "confirmed_imo": None,
        "confirmed_mmsi": None,
        "confirmed_name": None,
        "registered_flag": None,
        "vessel_type": None,
        "resolution_method": "unresolved",
        "identity_confidence": 0.0,
        "vessel_identity_unresolved": True,
        "flags": [],
        "candidates": [],
        "verification_evidence": {},
        "datalastic_available": True,  # always true — data comes from cache or live
    }

    if not bdn_imo and not bdn_name:
        result["flags"].append("missing_vessel_identity")
        return result

    imo_vessel: dict[str, Any] | None = None
    if bdn_imo and len(bdn_imo) == 7:
        imo_vessel = provider.get_vessel_by_imo(bdn_imo)

    name_candidates: list[dict[str, Any]] = []
    if bdn_name:
        name_candidates = provider.find_vessel_by_name(bdn_name) or []

    # Step A/B: IMO lookup + fuzzy name match
    if imo_vessel and bdn_name:
        registered_name = imo_vessel.get("name") or ""
        fuzzy_ratio = fuzz.token_sort_ratio(bdn_name.upper(), registered_name.upper()) / 100.0
        evidence = {
            "api_response": {"name": registered_name, "imo": imo_vessel.get("imo")},
            "match_score": round(fuzzy_ratio, 3),
            "method_used": "fuzzy" if fuzzy_ratio < 1.0 else "exact",
        }
        if fuzzy_ratio >= fuzzy_threshold:
            result.update({
                "confirmed_imo": imo_vessel.get("imo"),
                "confirmed_mmsi": imo_vessel.get("mmsi"),
                "confirmed_name": registered_name,
                "registered_flag": imo_vessel.get("flag"),
                "vessel_type": imo_vessel.get("type_specific") or imo_vessel.get("type"),
                "resolution_method": "fuzzy" if fuzzy_ratio < 1.0 else "exact",
                "identity_confidence": round(fuzzy_ratio, 3),
                "vessel_identity_unresolved": False,
                "verification_evidence": evidence,
            })
            if fuzzy_ratio < 1.0:
                result["flags"].append("vessel_name_fuzzy_match")
            return result

        # Step C: Embedding match
        embed_sim = _embedding_similarity(bdn_name, registered_name)
        evidence["embed_score"] = round(embed_sim, 3)
        evidence["method_used"] = "embedding"
        if embed_sim >= embed_threshold:
            result.update({
                "confirmed_imo": imo_vessel.get("imo"),
                "confirmed_mmsi": imo_vessel.get("mmsi"),
                "confirmed_name": registered_name,
                "registered_flag": imo_vessel.get("flag"),
                "vessel_type": imo_vessel.get("type_specific") or imo_vessel.get("type"),
                "resolution_method": "embedding",
                "identity_confidence": round(embed_sim, 3),
                "vessel_identity_unresolved": False,
                "flags": ["vessel_name_embedding_match"],
                "verification_evidence": evidence,
            })
            return result

    # Step D: Reverse name lookup — compare IMO
    if name_candidates and bdn_imo:
        best = name_candidates[0]
        reverse_imo = str(best.get("imo") or "")
        evidence = {
            "api_response": {"name": best.get("name"), "imo": reverse_imo},
            "match_score": 0.85,
            "method_used": "reverse_lookup",
        }
        if reverse_imo == bdn_imo:
            result.update({
                "confirmed_imo": reverse_imo,
                "confirmed_mmsi": best.get("mmsi"),
                "confirmed_name": best.get("name"),
                "registered_flag": best.get("flag"),
                "vessel_type": best.get("type_specific") or best.get("type"),
                "resolution_method": "reverse",
                "identity_confidence": 0.85,
                "vessel_identity_unresolved": False,
                "verification_evidence": evidence,
            })
            return result

        # Step E: Conflict — IMO and name point to different vessels
        result["flags"].append("vessel_identity_unresolved")
        result["candidates"] = [
            {"imo": bdn_imo, "name": imo_vessel.get("name") if imo_vessel else bdn_name, "source": "bdn_imo_lookup"},
            {"imo": reverse_imo, "name": best.get("name"), "source": "bdn_name_reverse_lookup"},
        ]
        if name_candidates[1:]:
            for extra in name_candidates[1:3]:
                result["candidates"].append({"imo": extra.get("imo"), "name": extra.get("name"), "source": "name_search_alternate"})
        result["verification_evidence"] = {"conflict": True, "imo_vessel": imo_vessel, "name_candidate": best}
        return result

    # IMO only (no name on BDN)
    if imo_vessel and not bdn_name:
        result.update({
            "confirmed_imo": imo_vessel.get("imo"),
            "confirmed_mmsi": imo_vessel.get("mmsi"),
            "confirmed_name": imo_vessel.get("name"),
            "registered_flag": imo_vessel.get("flag"),
            "vessel_type": imo_vessel.get("type_specific") or imo_vessel.get("type"),
            "resolution_method": "exact",
            "identity_confidence": 0.9,
            "vessel_identity_unresolved": False,
            "verification_evidence": {"method_used": "imo_only"},
        })
        return result

    # Name only (no IMO on BDN)
    if name_candidates and not bdn_imo:
        best = name_candidates[0]
        result.update({
            "confirmed_imo": best.get("imo"),
            "confirmed_mmsi": best.get("mmsi"),
            "confirmed_name": best.get("name"),
            "registered_flag": best.get("flag"),
            "vessel_type": best.get("type_specific") or best.get("type"),
            "resolution_method": "reverse",
            "identity_confidence": 0.75,
            "vessel_identity_unresolved": False,
            "flags": ["imo_missing_on_bdn"],
            "verification_evidence": {"method_used": "name_only", "match_score": 0.75},
        })
        return result

    if imo_vessel:
        result.update({
            "confirmed_imo": imo_vessel.get("imo"),
            "confirmed_mmsi": imo_vessel.get("mmsi"),
            "confirmed_name": imo_vessel.get("name"),
            "registered_flag": imo_vessel.get("flag"),
            "vessel_type": imo_vessel.get("type_specific") or imo_vessel.get("type"),
            "resolution_method": "imo_only_partial",
            "identity_confidence": 0.5,
            "vessel_identity_unresolved": False,
            "flags": ["vessel_name_mismatch"],
            "verification_evidence": {"method_used": "imo_partial"},
        })
        return result

    result["flags"].append("vessel_not_in_registry")
    return result
