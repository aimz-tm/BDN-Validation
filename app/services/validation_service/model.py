"""
Load Isolation Forest artifact and score AIS feature vectors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.core.config_loader import get_config
from app.services.validation_service.feature_names import FEATURE_NAMES

_artifact_cache: dict[str, Any] | None = None


def _artifact_paths() -> tuple[Path, Path]:
    cfg = get_config()["model"]
    base = Path(__file__).resolve().parents[3]
    model_path = base / cfg["artifact_path"]
    names_path = base / cfg.get("feature_names_path", "models_ml/feature_names.json")
    return model_path, names_path


def model_loaded() -> bool:
    path, _ = _artifact_paths()
    return path.exists()


def load_artifact(force_reload: bool = False) -> dict[str, Any] | None:
    global _artifact_cache
    if _artifact_cache is not None and not force_reload:
        return _artifact_cache

    model_path, names_path = _artifact_paths()
    if not model_path.exists():
        _artifact_cache = None
        return None

    bundle = joblib.load(model_path)
    if isinstance(bundle, dict) and "model" in bundle:
        _artifact_cache = bundle
    else:
        _artifact_cache = {"model": bundle, "feature_names": FEATURE_NAMES}

    if names_path.exists():
        with names_path.open("r", encoding="utf-8") as f:
            _artifact_cache["feature_names"] = json.load(f).get("feature_names", FEATURE_NAMES)

    return _artifact_cache


def score_feature_vector(vector: list[float]) -> dict[str, Any]:
    """
    Score one feature vector. Returns anomaly_score in [0, 1] and is_anomaly.
    If model missing, returns neutral score (does not crash).
    """
    cfg = get_config()
    threshold = float(cfg["model"]["isolation_forest"]["anomaly_score_threshold"])

    bundle = load_artifact()
    if bundle is None:
        return {
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "model_loaded": False,
            "message": "Isolation Forest artifact not found — run scripts/train_model.py",
        }

    model = bundle["model"]
    X = np.array([vector], dtype=np.float64)

    raw_scores = model.score_samples(X)
    raw = float(raw_scores[0])

    score_min = float(bundle.get("score_min", raw))
    score_max = float(bundle.get("score_max", raw))
    span = score_max - score_min
    if span <= 1e-12:
        anomaly_score = 0.5
    else:
        normalized = (raw - score_min) / span
        anomaly_score = round(max(0.0, min(1.0, 1.0 - normalized)), 4)

    is_anomaly = anomaly_score >= threshold

    return {
        "anomaly_score": anomaly_score,
        "is_anomaly": is_anomaly,
        "model_loaded": True,
        "raw_score_sample": raw,
    }
