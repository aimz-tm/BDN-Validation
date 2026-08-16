"""
scripts/seed_cache.py  (v3 — with proper timestamp handling)

WHAT YOU FILL IN per BDN:
  vessel_name, imo, barge_name, barge_sb, port, delivery_date
  start_time, end_time  — exactly as written on the BDN
  alongside_time        — only needed for handwritten BDNs (Format 3)

THE SCRIPT HANDLES:
  Format 1 — "2026-02-03 08:47:15"        (digital ISO)
  Format 2 — "02/03/2026 21:22"           (digital US date)
  Format 3 — "0150" with no date          (handwritten, inherits from alongside)
  Format 4 — "16:12 hrs. @ 25/11/2025"   (handwritten with @ separator)

  Midnight crossings are detected and fixed automatically.
  UTC conversion uses your ports.yaml timezone data.
  AIS window is fetched from start_date UTC to end_date UTC (never just one day).
"""

import json
import logging
import sys
import time
from datetime import timezone, timedelta
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import os

load_dotenv("config/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_cache")


# =============================================================================
# FILL THIS IN — one block per BDN
#
# start_time / end_time:
#   Copy exactly as it appears on the BDN. Examples:
#     "2026-02-03 08:47:15"     ← Format 1 (digital ISO)
#     "02/03/2026 21:22"        ← Format 2 (digital US date)
#     "0150"                    ← Format 3 (handwritten, time only)
#     "16:12 hrs. @ 25/11/2025" ← Format 4 (handwritten with @)
#
# alongside_time:
#   Only needed for Format 3 (handwritten with no date on pumping lines).
#   Copy the full "Alongside Vessel" line text, e.g. "1 MARCH 2026  0025"
#   Leave as None for all other formats.
# =============================================================================

BDN_DATA = [
    # ── BDN 1: Digital ISO format (Image 1) ──────────────────────────────────
    {
        "vessel_name":    "STAR ELIZABETH",
        "imo":            "9917488",
        "barge_name":     "MARINE ORACLE",
        "barge_sb":       "SB9333D",
        "port":           "Singapore",
        "delivery_date":  "2026-02-03",
        "start_time":     "2026-02-03 08:47:15",    # copy from BDN
        "end_time":       "2026-02-03 12:45:46",    # copy from BDN
        "alongside_time": None,                      # not needed for this format
    },

    # ── BDN 1: STAR ELIZABETH ───────────────────────────────────────────────
    {
        "vessel_name":    "STAR ELIZABETH",
        "imo":            "9917488",
        "barge_name":     "MARINE ORACLE",
        "barge_sb":       "SB9333D",
        "port":           "Singapore",
        "delivery_date":  "2026-02-03",
        "start_time":     "2026-02-03 08:47:15",
        "end_time":       "2026-02-03 12:45:46",
        "alongside_time": None,
    },

    # ── BDN 2: BERGE ACONCAGUA (HSFO) ───────────────────────────────────────
    {
        "vessel_name":    "BERGE ACONCAGUA",
        "imo":            "9447548",
        "barge_name":     "VANDA SUCCESS",
        "barge_sb":       "SB 0704G",
        "port":           "Singapore",
        "delivery_date":  "2026-02-11",
        "start_time":     "2026-02-10 23:05:29",
        "end_time":       "2026-02-11 13:57:24",
        "alongside_time": None,
    },

    # ── BDN 3: BERGE ACONCAGUA (LSMGO) ──────────────────────────────────────
    {
        "vessel_name":    "BERGE ACONCAGUA",
        "imo":            "9447548",
        "barge_name":     "LUMINOUS",
        "barge_sb":       "SB 0619I",
        "port":           "Singapore",
        "delivery_date":  "2026-02-11",
        "start_time":     "11-Feb-2026 18:04:15",
        "end_time":       "11-Feb-2026 21:10:15",
        "alongside_time": None,
    },

    # ── BDN 4: LUCKY PIONEER ────────────────────────────────────────────────
    {
        "vessel_name":    "LUCKY PIONEER",
        "imo":            "9537018",
        "barge_name":     "MT KHADIGA",
        "barge_sb":       None,
        "port":           "Fujairah",
        "delivery_date":  "2025-11-17",
        "start_time":     "17-11-2025 @ 1000 HRS",
        "end_time":       "17-11-2025 @ 1248 HRS",
        "alongside_time": None,
    },

    # ── BDN 5: MILOS I ──────────────────────────────────────────────────────
    {
        "vessel_name":    "MILOS I",
        "imo":            "1047677",
        "barge_name":     "FRONTEK",
        "barge_sb":       "SB 0742Z",
        "port":           "Singapore",
        "delivery_date":  "2026-02-27",
        "start_time":     "2026-02-27 20:32:48",
        "end_time":       "2026-02-27 22:26:04",
        "alongside_time": None,
    },
        # ── BDN 6: BERGE MERU (VLSFO) ───────────────────────────────────────────
    {
        "vessel_name":    "BERGE MERU",
        "imo":            "9855214",
        "barge_name":     "M/T Sea Abundance",
        "barge_sb":       "SB 0770E",
        "port":           "Singapore",
        "delivery_date":  "2026-04-19",
        "start_time":     "19/04/2026 18:38",
        "end_time":       "19/04/2026 20:09",
        "alongside_time": None,
    },

    # ── BDN 7: BERGE MERU (LSMGO) ───────────────────────────────────────────
    {
        "vessel_name":    "BERGE MERU",
        "imo":            "9855214",
        "barge_name":     "M/T Sea Harvest",
        "barge_sb":       "SB 8118B",
        "port":           "Singapore",
        "delivery_date":  "2026-04-19",
        "start_time":     "19/04/2026 23:13",
        "end_time":       "20/04/2026 00:20",
        "alongside_time": None,
    },

    # ── BDN 8: BERGE MERU (HSFO) ────────────────────────────────────────────
    {
        "vessel_name":    "BERGE MERU",
        "imo":            "9855214",
        "barge_name":     "M/T Sea Loyalty",
        "barge_sb":       "SB 0765I",
        "port":           "Singapore",
        "delivery_date":  "2026-04-20",
        "start_time":     "20/04/2026 00:22",
        "end_time":       "20/04/2026 14:30",
        "alongside_time": None,
    },

    # ── BDN 9: BERGE GROSSGLOCKNER (HSFO) ───────────────────────────────────
    {
        "vessel_name":    "BERGE GROSSGLOCKNER",
        "imo":            "9750921",
        "barge_name":     "M/T Sea Diligence",
        "barge_sb":       "SB 0801I",
        "port":           "Singapore",
        "delivery_date":  "2026-03-02",
        "start_time":     "02/03/2026 21:22",
        "end_time":       "03/03/2026 02:00",
        "alongside_time": None,
    },

    # ── BDN 10: GREAT PEACE (Handwritten) ───────────────────────────────────
    {
        "vessel_name":    "GREAT PEACE",
        "imo":            "9256884",
        "barge_name":     "LS MORALITY",
        "barge_sb":       None,
        "port":           "Hong Kong",
        "delivery_date":  "2026-02-15",
        "start_time":     "1850",
        "end_time":       "1945",
        "alongside_time": "15 FEB 2026 1810",
    },

    # ── BDN 11: OBE ODYSSEY (VLSFO) ─────────────────────────────────────────
    {
        "vessel_name":    "OBE ODYSSEY",
        "imo":            "9986946",
        "barge_name":     "INTAN GLORY",
        "barge_sb":       None,
        "port":           "Fujairah",
        "delivery_date":  "2025-11-25",
        "start_time":     "15:12 hrs. @ 25/11/2025",
        "end_time":       "18:12 hrs. @ 25/11/2025",
        "alongside_time": None,
    },

    # ── BDN 12: OBE ODYSSEY (LSMGO) ─────────────────────────────────────────
    {
        "vessel_name":    "OBE ODYSSEY",
        "imo":            "9986946",
        "barge_name":     "INTAN GLORY",
        "barge_sb":       None,
        "port":           "Fujairah",
        "delivery_date":  "2025-11-25",
        "start_time":     "16:24 hrs. @ 25/11/2025",
        "end_time":       "16:36 hrs. @ 25/11/2025",
        "alongside_time": None,
    },

    # ── BDN 13: OSAKA STAR (Handwritten) ────────────────────────────────────
    {
        "vessel_name":    "OSAKA STAR",
        "imo":            "9740809",
        "barge_name":     "LS MORALITY",
        "barge_sb":       None,
        "port":           "Hong Kong",
        "delivery_date":  "2026-03-01",
        "start_time":     "0150",
        "end_time":       "0805",
        "alongside_time": "1 MARCH 2026 0025",
    },
]
# =============================================================================
# NOTHING BELOW NEEDS CHANGING
# =============================================================================

BASE_URL   = "https://api.datalastic.com/api/v0"
CACHE_DIR  = Path("data/ais_cache")
API_KEY    = os.environ.get("DATALASTIC_API_KEY", "")
TIMEOUT    = 10
SSL_VERIFY = False


# ── Timezone lookup ───────────────────────────────────────────────────────────

def _load_port_timezones() -> dict:
    """Load UTC offsets from timezone_service/ports.yaml"""
    ports_file = Path("services/timezone_service/ports.yaml")
    if not ports_file.exists():
        logger.warning("ports.yaml not found — assuming UTC+8 for all ports")
        return {}
    with open(ports_file) as f:
        raw = yaml.safe_load(f)
    result = {}
    for port_name, info in raw.items():
        if isinstance(info, dict):
            offset = info.get("utc_offset") or info.get("timezone_offset") or info.get("offset")
            if offset is not None:
                result[port_name] = float(offset)
    return result


def _get_utc_offset(port: str, tz_map: dict) -> float:
    """Return UTC offset in hours for a port. Default Singapore = +8."""
    for key in tz_map:
        if port.lower() in key.lower() or key.lower() in port.lower():
            return tz_map[key]
    logger.warning("Port '%s' not in ports.yaml — defaulting to UTC+8 (Singapore)", port)
    return 8.0


# ── Timestamp parsing ─────────────────────────────────────────────────────────

def _parse_and_convert(start_raw: str, end_raw: str, alongside_raw, port: str, tz_map: dict):
    """
    Parse pumping times and convert to UTC.
    Returns (utc_date_from, utc_date_to) as "YYYY-MM-DD" strings.
    These are the dates to pass to Datalastic vessel_history.
    """
    from app.services.extraction_service.timestamp_normalizer import parse_pumping_times

    parsed = parse_pumping_times(start_raw, end_raw, alongside_raw)

    if parsed.get("error"):
        logger.warning("  Timestamp parse failed: %s", parsed["error"])
        logger.warning("  Falling back to delivery_date ± 1 day for AIS window")
        return None, None

    logger.info("  Timestamps parsed [%s]:", parsed["parse_format"])
    logger.info("    Start (local): %s", parsed["start_str"])
    logger.info("    End   (local): %s", parsed["end_str"])
    if parsed["crossed_midnight"]:
        logger.info("    ⚠ Midnight crossing detected — end date advanced by 1 day")
    if parsed["inherited_date"]:
        logger.info("    ℹ Date inherited from Alongside Vessel line")

    # Convert local time → UTC
    utc_offset = _get_utc_offset(port, tz_map)
    offset     = timedelta(hours=utc_offset)

    start_utc = parsed["start_dt"] - offset
    end_utc   = parsed["end_dt"]   - offset

    logger.info("    UTC offset: +%.0f hrs", utc_offset)
    logger.info("    Start (UTC): %s", start_utc.strftime("%Y-%m-%d %H:%M"))
    logger.info("    End   (UTC): %s", end_utc.strftime("%Y-%m-%d %H:%M"))

    return start_utc.strftime("%Y-%m-%d"), end_utc.strftime("%Y-%m-%d")


# ── Datalastic API ────────────────────────────────────────────────────────────

def _get(endpoint: str, params: dict) -> dict | None:
    params = {**params, "api-key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT, verify=SSL_VERIFY)
            r.raise_for_status()
            return r.json()
        except requests.Timeout:
            logger.warning("    Timeout (attempt %d/3)...", attempt + 1)
            time.sleep(2)
        except requests.RequestException as e:
            logger.error("    Request failed: %s", e)
            return None
    return None


def _write(filename: str, data) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    size_kb = round(path.stat().st_size / 1024, 1)
    logger.info("    ✓ Saved → %s  (%s kb)", filename, size_kb)


# ── Seeders ───────────────────────────────────────────────────────────────────

def fetch_vessel_by_imo(imo: str) -> str | None:
    logger.info("  [API 1] Vessel lookup IMO=%s", imo)
    data = _get("vessel", {"imo": imo})
    if not data or not data.get("data"):
        logger.warning("    ✗ Not found")
        return None
    vessel = data["data"]
    _write(f"vessel_imo_{imo}.json", vessel)
    mmsi = vessel.get("mmsi") or vessel.get("mmsi_number")
    logger.info("    MMSI = %s", mmsi)
    return mmsi


def fetch_vessel_by_name(vessel_name: str) -> None:
    logger.info("  [API 2] Vessel name search '%s'", vessel_name)
    data = _get("vessel_find", {"name": vessel_name})
    if data and data.get("data"):
        slug = vessel_name.lower().replace(" ", "_")
        _write(f"vessel_search_{slug}.json", data["data"])
        logger.info("    %d result(s)", len(data["data"]))
    else:
        logger.warning("    ✗ No results")


def fetch_barge_by_name(barge_name: str) -> str | None:
    slug  = barge_name.lower().replace(" ", "_")
    mmsi  = None

    logger.info("  [API 3] Barge search '%s' (tanker filter)", barge_name)
    data = _get("vessel_find", {"name": barge_name, "type_specific": "tanker"})
    if data and data.get("data"):
        _write(f"vessel_search_{slug}_tanker.json", data["data"])
        mmsi = data["data"][0].get("mmsi") or data["data"][0].get("mmsi_number")
        logger.info("    %d result(s)  MMSI=%s", len(data["data"]), mmsi)
    else:
        logger.info("    No tanker results")

    logger.info("  [API 4] Barge search '%s' (no type filter)", barge_name)
    data2 = _get("vessel_find", {"name": barge_name})
    if data2 and data2.get("data"):
        _write(f"vessel_search_{slug}_any.json", data2["data"])
        if not mmsi:
            mmsi = data2["data"][0].get("mmsi") or data2["data"][0].get("mmsi_number")
        logger.info("    %d result(s)  MMSI=%s", len(data2["data"]), mmsi)
    else:
        logger.warning("    ✗ No results")

    return mmsi


def fetch_inradius(port: str, tz_map: dict) -> None:
    ports_file = Path("services/timezone_service/ports.yaml")
    if not ports_file.exists():
        logger.info("  [API 5] Skipped — ports.yaml not found")
        return
    with open(ports_file) as f:
        raw = yaml.safe_load(f)
    port_info = None
    for key, info in raw.items():
        if port.lower() in key.lower() or key.lower() in port.lower():
            port_info = info
            break
    if not port_info or "lat" not in port_info:
        logger.info("  [API 5] Skipped — no coordinates for port '%s' in ports.yaml", port)
        return

    lat, lon = port_info["lat"], port_info["lon"]
    logger.info("  [API 5] Inradius search lat=%s lon=%s radius=5km", lat, lon)
    data = _get("vessel_inradius", {"lat": lat, "lon": lon, "radius": 5.0, "type_specific": "tanker"})
    if data and data.get("data"):
        slug = f"{round(lat,4)}_{round(lon,4)}".replace(".", "_")
        _write(f"vessel_radius_{slug}.json", data["data"])
        logger.info("    %d vessel(s) in radius", len(data["data"]))
    else:
        logger.info("    No vessels in radius")


def fetch_ais_history(mmsi: str, label: str, date_from: str, date_to: str) -> None:
    logger.info("  [API 6] AIS history  MMSI=%s (%s)  %s → %s", mmsi, label, date_from, date_to)
    data = _get("vessel_history", {"mmsi": mmsi, "from": date_from, "to": date_to})
    if data and data.get("data"):
        filename = f"ais_history_{mmsi}_{date_from}_{date_to}.json"
        _write(filename, data["data"])
        logger.info("    %d GPS positions", len(data["data"]))
    else:
        logger.warning("    ✗ No GPS positions in this window")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY:
        logger.error("DATALASTIC_API_KEY not set in config/.env")
        sys.exit(1)

    tz_map = _load_port_timezones()
    logger.info("Loaded timezones for: %s", list(tz_map.keys()) or ["(none — will use UTC+8)"])

    logger.info("=" * 64)
    logger.info("Datalastic Cache Seeder  —  %d BDN entries", len(BDN_DATA))
    logger.info("=" * 64)

    ok = fail = 0

    for i, bdn in enumerate(BDN_DATA, 1):
        logger.info(
            "\n[%d/%d] %s  /  %s  —  %s",
            i, len(BDN_DATA),
            bdn["vessel_name"], bdn["barge_name"], bdn["delivery_date"]
        )
        logger.info("-" * 56)

        # ── Parse timestamps → get correct UTC date window ────────────────
        date_from, date_to = _parse_and_convert(
            bdn["start_time"],
            bdn["end_time"],
            bdn.get("alongside_time"),
            bdn["port"],
            tz_map,
        )

        # Fallback: delivery_date ± 1 day if parsing failed
        if not date_from:
            from datetime import date, timedelta
            d = date.fromisoformat(bdn["delivery_date"])
            date_from = (d - timedelta(days=1)).isoformat()
            date_to   = (d + timedelta(days=1)).isoformat()
            logger.info("  Using fallback window: %s → %s", date_from, date_to)

        # ── Vessel ────────────────────────────────────────────────────────
        vessel_mmsi = fetch_vessel_by_imo(bdn["imo"])
        fetch_vessel_by_name(bdn["vessel_name"])

        if vessel_mmsi:
            fetch_ais_history(vessel_mmsi, bdn["vessel_name"], date_from, date_to)
            ok += 1
        else:
            logger.warning("  No vessel MMSI — skipping vessel GPS")
            fail += 1

        # ── Barge ─────────────────────────────────────────────────────────
        barge_mmsi = fetch_barge_by_name(bdn["barge_name"])
        fetch_inradius(bdn["port"], tz_map)

        if barge_mmsi:
            fetch_ais_history(barge_mmsi, bdn["barge_name"], date_from, date_to)
            ok += 1
        else:
            logger.warning("  No barge MMSI — barge GPS not cached for this entry")
            fail += 1

    logger.info("\n" + "=" * 64)
    logger.info("Done.  ✓ %d GPS tracks saved    ✗ %d missing", ok, fail)
    logger.info("")
    logger.info("Now set in config/config.yaml:")
    logger.info("  data_provider:")
    logger.info("    mode: cached")
    logger.info("=" * 64)


if __name__ == "__main__":
    main()