import json
from services.ais_service.validate import run_ais_validation
identity = {
    "vessel_identity_unresolved": False,
    "confirmed_imo": "9876543",
    "confirmed_mmsi": "538009999",
    "confirmed_name": "STAR PHOENIX TANKER"
}
extraction = {
    "quantity_mt": 485.5,
    "port": "Singapore",
    "start_time": "15 May 2026 08:00",
    "end_time": "15 May 2026 11:12",
    "delivery_date": "15 May 2026"
}
res = run_ais_validation(identity, extraction)
print(json.dumps(res, indent=2))
