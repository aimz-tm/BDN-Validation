"""
Vessel identity resolution — cross-validate BDN IMO and name against registry.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def token_sort_ratio(a: str, b: str) -> float:
            a_sorted = " ".join(sorted(a.split()))
            b_sorted = " ".join(sorted(b.split()))
            return SequenceMatcher(None, a_sorted, b_sorted).ratio() * 100.0

    fuzz = _FuzzFallback()

from app.core.config_loader import get_config
from app.services.identity_service import datalastic_client


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
    Steps A–E from spec. Never trust BDN identity without registry cross-check.
    """
    cfg = get_config()["identity"]
    fuzzy_threshold = float(cfg["fuzzy_match_threshold"])
    embed_threshold = float(cfg["embedding_similarity_threshold"])

    bdn_name = (extraction.get("vessel_name") or "").strip()
    bdn_imo = re.sub(r"\D", "", str(extraction.get("imo") or ""))

    result: dict[str, Any] = {
        "bdn_name": bdn_name or None,
        "bdn_imo": bdn_imo or None,
        "confirmed_imo": None,
        "confirmed_mmsi": None,
        "confirmed_name": None,
        "resolution_method": "unresolved",
        "identity_confidence": 0.0,
        "vessel_identity_unresolved": True,
        "flags": [],
        "candidates": [],
        "datalastic_available": bool(datalastic_client._api_key()),
    }

    if not bdn_imo and not bdn_name:
        result["flags"].append("missing_vessel_identity")
        return result

    imo_vessel: dict[str, Any] | None = None
    if bdn_imo and len(bdn_imo) == 7:
        imo_vessel = datalastic_client.get_vessel_by_imo(bdn_imo)

    name_candidates: list[dict[str, Any]] = []
    if bdn_name:
        name_candidates = datalastic_client.search_vessel_by_name(bdn_name)

    # Step A/B: IMO lookup + fuzzy name match
    if imo_vessel and bdn_name:
        registered_name = imo_vessel.get("name") or ""
        fuzzy_ratio = fuzz.token_sort_ratio(bdn_name.upper(), registered_name.upper()) / 100.0
        if fuzzy_ratio >= fuzzy_threshold:
            result.update(
                {
                    "confirmed_imo": imo_vessel.get("imo"),
                    "confirmed_mmsi": imo_vessel.get("mmsi"),
                    "confirmed_name": registered_name,
                    "resolution_method": "fuzzy" if fuzzy_ratio < 1.0 else "exact",
                    "identity_confidence": round(fuzzy_ratio, 3),
                    "vessel_identity_unresolved": False,
                }
            )
            if fuzzy_ratio < 1.0:
                result["flags"].append("vessel_name_fuzzy_match")
            return result

        embed_sim = _embedding_similarity(bdn_name, registered_name)
        if embed_sim >= embed_threshold:
            result.update(
                {
                    "confirmed_imo": imo_vessel.get("imo"),
                    "confirmed_mmsi": imo_vessel.get("mmsi"),
                    "confirmed_name": registered_name,
                    "resolution_method": "embedding",
                    "identity_confidence": round(embed_sim, 3),
                    "vessel_identity_unresolved": False,
                    "flags": ["vessel_name_embedding_match"],
                }
            )
            return result

    # Step C/D: reverse name lookup — compare IMO
    if name_candidates and bdn_imo:
        best = name_candidates[0]
        reverse_imo = str(best.get("imo") or "")
        if reverse_imo == bdn_imo:
            result.update(
                {
                    "confirmed_imo": reverse_imo,
                    "confirmed_mmsi": best.get("mmsi"),
                    "confirmed_name": best.get("name"),
                    "resolution_method": "reverse",
                    "identity_confidence": 0.85,
                    "vessel_identity_unresolved": False,
                }
            )
            return result

        # Step E: IMO and name point to different vessels
        result["flags"].append("vessel_identity_unresolved")
        result["candidates"] = [
            {
                "imo": bdn_imo,
                "name": imo_vessel.get("name") if imo_vessel else bdn_name,
                "source": "bdn_imo_lookup",
            },
            {
                "imo": reverse_imo,
                "name": best.get("name"),
                "source": "bdn_name_reverse_lookup",
            },
        ]
        if name_candidates[1:]:
            for extra in name_candidates[1:3]:
                result["candidates"].append(
                    {
                        "imo": extra.get("imo"),
                        "name": extra.get("name"),
                        "source": "name_search_alternate",
                    }
                )
        return result

    # IMO only — accept without name on BDN
    if imo_vessel and not bdn_name:
        result.update(
            {
                "confirmed_imo": imo_vessel.get("imo"),
                "confirmed_mmsi": imo_vessel.get("mmsi"),
                "confirmed_name": imo_vessel.get("name"),
                "resolution_method": "exact",
                "identity_confidence": 0.9,
                "vessel_identity_unresolved": False,
            }
        )
        return result

    # Name only
    if name_candidates and not bdn_imo:
        best = name_candidates[0]
        result.update(
            {
                "confirmed_imo": best.get("imo"),
                "confirmed_mmsi": best.get("mmsi"),
                "confirmed_name": best.get("name"),
                "resolution_method": "reverse",
                "identity_confidence": 0.75,
                "vessel_identity_unresolved": False,
                "flags": ["imo_missing_on_bdn"],
            }
        )
        return result

    if imo_vessel:
        result.update(
            {
                "confirmed_imo": imo_vessel.get("imo"),
                "confirmed_mmsi": imo_vessel.get("mmsi"),
                "confirmed_name": imo_vessel.get("name"),
                "resolution_method": "imo_only_partial",
                "identity_confidence": 0.5,
                "vessel_identity_unresolved": False,
                "flags": ["vessel_name_mismatch"],
            }
        )
        return result

    result["flags"].append("vessel_not_in_registry")
    return result
