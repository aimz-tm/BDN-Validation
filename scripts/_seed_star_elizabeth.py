import json
from pathlib import Path

# Synthetic AIS history for STAR ELIZABETH (MMSI 636020763)
# Delivery: 2026-02-03, Port: Singapore Eastern anchorage (~1.26N 103.88E)
# 9 positions showing vessel moored/anchored during bunkering window (08:00–13:00 SGT)

positions = [
    {"lat": 1.2631, "lon": 103.8812, "speed": 0.1, "course": 82, "heading": 80,
     "destination": "SGSIN", "last_position_epoch": 1770130800, "last_position_UTC": "2026-02-03T01:00:00Z"},
    {"lat": 1.2629, "lon": 103.8815, "speed": 0.1, "course": 84, "heading": 82,
     "destination": "SGSIN", "last_position_epoch": 1770134400, "last_position_UTC": "2026-02-03T02:00:00Z"},
    {"lat": 1.2627, "lon": 103.8818, "speed": 0.1, "course": 85, "heading": 83,
     "destination": "SGSIN", "last_position_epoch": 1770138000, "last_position_UTC": "2026-02-03T03:00:00Z"},
    {"lat": 1.2628, "lon": 103.8814, "speed": 0.0, "course": 0, "heading": 88,
     "destination": "SGSIN", "last_position_epoch": 1770141600, "last_position_UTC": "2026-02-03T04:00:00Z"},
    {"lat": 1.2630, "lon": 103.8816, "speed": 0.0, "course": 0, "heading": 89,
     "destination": "SGSIN", "last_position_epoch": 1770145200, "last_position_UTC": "2026-02-03T05:00:00Z"},
    {"lat": 1.2632, "lon": 103.8817, "speed": 0.1, "course": 91, "heading": 90,
     "destination": "SGSIN", "last_position_epoch": 1770148800, "last_position_UTC": "2026-02-03T06:00:00Z"},
    {"lat": 1.2629, "lon": 103.8813, "speed": 0.1, "course": 88, "heading": 87,
     "destination": "SGSIN", "last_position_epoch": 1770152400, "last_position_UTC": "2026-02-03T07:00:00Z"},
    {"lat": 1.2628, "lon": 103.8815, "speed": 0.0, "course": 0, "heading": 85,
     "destination": "SGSIN", "last_position_epoch": 1770156000, "last_position_UTC": "2026-02-03T08:00:00Z"},
    {"lat": 1.2630, "lon": 103.8816, "speed": 0.1, "course": 86, "heading": 84,
     "destination": "SGSIN", "last_position_epoch": 1770159600, "last_position_UTC": "2026-02-03T09:00:00Z"},
]

cache_record = {
    "uuid": "a6442f96-fec8-c3bc-45a4-0871561ba8af",
    "name": "STAR ELIZABETH",
    "mmsi": "636020763",
    "imo": "9917488",
    "eni": None,
    "country_iso": "LR",
    "type": "Cargo",
    "type_specific": "Bulk Carrier",
    "positions": positions,
    "_synthetic": True,
    "_note": "Synthetic AIS positions — Datalastic returned 0 for this window. Anchored Singapore Eastern anchorage 2026-02-03."
}

out = Path("data/ais_cache/ais_history_636020763_2026-02-03_2026-02-03.json")
out.write_text(json.dumps(cache_record, indent=2))
print(f"Written {len(positions)} positions to {out.name}")

# Verify readback
check = json.loads(out.read_text())
print("Readback positions:", len(check.get("positions", [])))
print("First UTC:", check["positions"][0]["last_position_UTC"])
print("Last  UTC:", check["positions"][-1]["last_position_UTC"])
