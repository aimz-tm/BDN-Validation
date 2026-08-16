#!/usr/bin/env python3
"""
Train Isolation Forest on SYNTHETIC normal bunkering patterns.

You do NOT need historical AIS data or labelled fraud cases.
Sample BDN images only help calibrate quantity/duration (optional):
  python scripts/calibrate_from_bdns.py

Usage (from repo root):
  python scripts/train_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config_loader import get_config
from app.services.validation_service.feature_names import FEATURE_NAMES
from app.services.validation_service.synthetic_data import generate_training_matrix


def main() -> None:
    config = get_config()
    model_cfg = config["model"]
    iforest_cfg = model_cfg["isolation_forest"]
    out_dir = ROOT / Path(model_cfg["artifact_path"]).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = ROOT / model_cfg["artifact_path"]
    names_path = ROOT / model_cfg.get("feature_names_path", "models_ml/feature_names.json")

    print("Generating synthetic training data (normal bunkering + injected anomalies)...")
    X, y = generate_training_matrix()
    print(f"  samples: {X.shape[0]}, features: {X.shape[1]}")
    print(f"  normal: {(y == 0).sum()}, anomaly-injected: {(y == 1).sum()}")

    clf = IsolationForest(
        n_estimators=int(iforest_cfg["n_estimators"]),
        contamination=float(iforest_cfg["contamination"]),
        random_state=int(iforest_cfg["random_state"]),
    )
    clf.fit(X)

    train_scores = clf.score_samples(X)
    bundle = {
        "model": clf,
        "feature_names": FEATURE_NAMES,
        "score_min": float(np.min(train_scores)),
        "score_max": float(np.max(train_scores)),
        "trained_on": "synthetic",
        "n_samples": int(X.shape[0]),
    }

    joblib.dump(bundle, model_path)
    with names_path.open("w", encoding="utf-8") as f:
        json.dump({"feature_names": FEATURE_NAMES}, f, indent=2)

    preds = clf.predict(X)
    n_flagged = int((preds == -1).sum())
    print(f"Model saved: {model_path}")
    print(f"Feature names: {names_path}")
    print(f"Training flagged {n_flagged}/{len(preds)} samples as outliers (expected ~{iforest_cfg['contamination']*100:.0f}%)")


if __name__ == "__main__":
    main()
