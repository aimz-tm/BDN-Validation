import json
from pathlib import Path

cache = Path("data/ais_cache")

# STAR ELIZABETH
p = cache / "ais_history_636020763_2026-02-03_2026-02-03.json"
d = json.loads(p.read_text())
print("STAR ELIZABETH file size:", p.stat().st_size, "bytes")
print("Positions in file:", len(d.get("positions", [])))

print()
all_se = list(cache.glob("ais_history_636020763_*.json"))
print("All AIS files for MMSI 636020763:")
for f in all_se:
    dd = json.loads(f.read_text())
    print(f"  {f.name}: {len(dd.get('positions', []))} positions")

print()
ba = cache / "ais_history_235090341_2026-02-10_2026-02-12.json"
bd = json.loads(ba.read_text())
positions = bd.get("positions", [])
print("BERGE ACONCAGUA positions in cache:", len(positions))
if positions:
    print("First position UTC:", positions[0].get("last_position_UTC"))
    print("Last  position UTC:", positions[-1].get("last_position_UTC"))
