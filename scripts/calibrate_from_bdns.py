#!/usr/bin/env python3
"""
Scan sample BDN files to suggest synthetic training priors (quantity, duration).

Your sample BDNs do NOT train the Isolation Forest — they calibrate realistic
ranges for document-linked features (quantity_feasibility) and optional config tuning.

Place images in fixtures/sample_bdns/ (or set model.calibration.sample_bdn_dir in config).

  python scripts/calibrate_from_bdns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config_loader import get_config
from app.services.document_service.pipeline import process_bdn


def main() -> None:
    cfg = get_config()
    sample_dir = ROOT / cfg["model"]["calibration"]["sample_bdn_dir"]
    if not sample_dir.exists():
        sample_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created {sample_dir} — add your sample BDN PNG/JPEG files and re-run.")
        return

    extensions = {".png", ".jpg", ".jpeg", ".pdf"}
    files = [f for f in sample_dir.iterdir() if f.suffix.lower() in extensions]
    if not files:
        print(f"No BDN files in {sample_dir}")
        return

    quantities: list[float] = []
    durations: list[float] = []

    for path in files:
        print(f"Processing {path.name}...")
        try:
            result = process_bdn(str(path))
            ext = result.get("extraction") or {}
            qty = ext.get("quantity_mt")
            if qty is not None:
                quantities.append(float(qty))
            start = ext.get("start_time")
            end = ext.get("end_time")
            if start and end:
                from datetime import datetime

                fmt = "%d %B %Y %H:%M"
                try:
                    t1 = datetime.strptime(start, fmt)
                    t2 = datetime.strptime(end, fmt)
                    durations.append((t2 - t1).total_seconds() / 3600.0)
                except ValueError:
                    pass
        except Exception as exc:
            print(f"  skipped: {exc}")

    print("\n--- Suggested config hints (paste into config.yaml if useful) ---")
    if quantities:
        print(f"  Sample quantities (MT): min={min(quantities):.1f} max={max(quantities):.1f} avg={sum(quantities)/len(quantities):.1f}")
    if durations:
        print(f"  Sample durations (h): min={min(durations):.2f} max={max(durations):.2f}")
        print("  model.training.delivery_duration_hours_min / max — align with your BDNs")
    print("\nNext: train the ML model (no AIS data required):")
    print("  python scripts/train_model.py")


if __name__ == "__main__":
    main()
