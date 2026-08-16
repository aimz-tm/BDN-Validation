"""Ordered feature vector columns for the Isolation Forest (must match training)."""

# NOTE: build_feature_vector() (services/validation_service/features.py) only
# computes the AIS/Geospatial group below, and models_ml/isolation_forest.pkl
# was trained on exactly these 9 columns (see models_ml/feature_names.json).
# Document-quality/identity/fraud signals (ocr_confidence, barge_verified,
# marpol_violation, etc.) are NOT included here yet — adding them requires
# both computing them in build_feature_vector() and retraining the model.
FEATURE_NAMES = [
    # ── AIS / Geospatial ──────────────────────────────────────────
    "mean_vessel_barge_distance_m",
    "var_vessel_barge_distance_m",
    "vessel_speed_mean",
    "vessel_speed_var",
    "heading_correlation",
    "colocation_ratio",
    "position_drift_rate",
    "port_distance_km",
    "quantity_feasibility",
]
