"""Ordered feature vector columns for the Isolation Forest (must match training)."""

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
    # ── Document quality ──────────────────────────────────────────
    # These signals are computed by the rule engine on every BDN.
    # Including them lets the model catch document-level fraud even
    # when AIS data is unavailable or synthetic.
    "ocr_confidence",           # Tesseract mean word confidence [0, 1]
    "field_completeness",       # fraction of required fields extracted [0, 1]
    "credibility_score_norm",   # credibility scorer output / 100 → [0, 1]
    "extraction_confidence",    # extractor's own confidence estimate [0, 1]
    "is_handwritten",           # 1 = HANDWRITTEN doc (inherently noisier)
    # ── Identity & verification ───────────────────────────────────
    "identity_confidence",      # vessel registry match depth [0, 1]
    "barge_verified",           # 1 = barge found in MPA registry
    # ── Fraud signals ─────────────────────────────────────────────
    "fraud_alert_count",        # total fraud alerts generated
    "high_severity_alerts",     # alerts with severity = HIGH
    "marpol_violation",         # 1 = at least one MARPOL limit exceeded
]
