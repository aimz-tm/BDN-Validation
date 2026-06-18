"""
ML scorer — Phase 6.
Loads models_ml/isolation_forest.pkl.
All hyperparameters from config.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config_loader import get_config

_model_cache: Any = None


def _model_path() -> Path:
    cfg = get_config()
    return Path(cfg.get("model", {}).get("artifact_path", "models_ml/isolation_forest.pkl"))


def model_loaded() -> bool:
    return _model_path().exists()


def load_model() -> Any:
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    path = _model_path()
    if not path.exists():
        return None
    try:
        import pickle
        with open(path, "rb") as f:
            _model_cache = pickle.load(f)
        return _model_cache
    except Exception:
        return None


def score_feature_vector(vector: list[float]) -> dict[str, Any]:
    """
    Score using Isolation Forest.
    Returns: { anomaly_score, is_anomaly, model_loaded }
    """
    cfg = get_config()
    threshold = float(cfg["model"]["isolation_forest"]["anomaly_score_threshold"])
    model = load_model()

    if model is None:
        return {"anomaly_score": 0.5, "is_anomaly": False, "model_loaded": False}

    try:
        import numpy as np
        X = np.array(vector).reshape(1, -1)
        raw_score = float(model.score_samples(X)[0])
        # Isolation Forest: lower score = more anomalous. Normalize to 0-1 (0=normal, 1=anomaly)
        anomaly_score = max(0.0, min(1.0, -raw_score))
        is_anomaly = anomaly_score >= threshold
        return {"anomaly_score": round(anomaly_score, 3), "is_anomaly": is_anomaly, "model_loaded": True}
    except Exception:
        return {"anomaly_score": 0.5, "is_anomaly": False, "model_loaded": False}
