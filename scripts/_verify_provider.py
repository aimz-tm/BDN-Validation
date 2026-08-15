from services.data_provider.factory import get_data_provider, reset_provider
reset_provider()  # clear singleton so we re-read config fresh
p = get_data_provider()
print("Provider:", type(p).__name__)
v = p.get_vessel_by_imo("9917488")
print("Vessel:", v.get("name"), "— MMSI:", v.get("mmsi"))
h = p.get_ais_history("636020763", "2026-02-03", "2026-02-03")
print("AIS positions:", len(h))
