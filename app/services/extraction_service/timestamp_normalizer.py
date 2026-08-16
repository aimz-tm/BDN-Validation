"""
services/extraction_service/timestamp_normalizer.py

Parses pumping timestamps from all known BDN formats into a
standard dict the rest of the pipeline can use.

Handles all 4 formats seen across real BDNs:

  FORMAT 1 — Digital ISO (e.g. BP digital BDN)
    "2026-02-03 08:47:15"
    "2026-02-03 12:45:46"

  FORMAT 2 — Digital US date, may cross midnight
    "02/03/2026 21:22"
    "03/03/2026 02:00"   ← next day

  FORMAT 3 — Handwritten, time only, date inherited from Alongside line
    Alongside:         "1 MARCH 2026  0025"
    Commenced:         "0150"           ← no date
    Completed:         "0805"           ← no date

  FORMAT 4 — Handwritten with "hrs. @" separator
    "16:12 hrs. @ 25/11/2025"
    "18:12 hrs. @ 25/11/2025"

Output (always):
    {
        "start_dt":   datetime object (UTC-naive, local port time)
        "end_dt":     datetime object (UTC-naive, local port time)
        "start_str":  "2026-02-03 08:47"   (normalised string)
        "end_str":    "2026-02-03 12:45"
        "crossed_midnight": True/False
        "inherited_date":   True/False   (Format 3 only)
        "parse_format":     "ISO" | "US_DATE" | "INHERITED" | "HRS_AT"
    }
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

def parse_pumping_times(
    start_raw: str,
    end_raw: str,
    alongside_raw: Optional[str] = None,
) -> dict:
    """
    Parse start and end pumping times from raw OCR strings.

    Args:
        start_raw:      Raw OCR text for "Commenced Pumping" field
        end_raw:        Raw OCR text for "Completed Pumping" field
        alongside_raw:  Raw OCR text for "Alongside Vessel" field
                        (needed for Format 3 date inheritance)

    Returns:
        Normalised dict described in module docstring.
        Returns None values if parsing fails — never raises.
    """
    if not start_raw or not end_raw:
        return _failed("empty input")

    start_raw = start_raw.strip()
    end_raw   = end_raw.strip()

    # Try each format in order of specificity
    for parser in [_parse_iso, _parse_us_date, _parse_hrs_at, _parse_date_at_hrs, _parse_time_only]:
        result = parser(start_raw, end_raw, alongside_raw)
        if result:
            # Fix midnight crossing regardless of which format parsed it
            result = _fix_midnight_crossing(result)
            logger.debug(
                "Parsed pumping times [%s]: %s → %s  (midnight=%s)",
                result["parse_format"],
                result["start_str"],
                result["end_str"],
                result["crossed_midnight"],
            )
            return result

    logger.warning(
        "Could not parse pumping times — start='%s'  end='%s'",
        start_raw, end_raw
    )
    return _failed(f"no format matched: start='{start_raw}' end='{end_raw}'")


# ── Format 1: ISO  "2026-02-03 08:47:15" ─────────────────────────────────────

def _parse_iso(start_raw: str, end_raw: str, _alongside=None) -> Optional[dict]:
    patterns = [
        r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})(?::\d{2})?",   # 2026-02-03 08:47:15
        r"(\d{2}-[A-Za-z]{3}-\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)", # 11-Feb-2026 18:04:15 
    ]
    start_dt = _try_patterns(start_raw, patterns)
    end_dt   = _try_patterns(end_raw, patterns)
    if start_dt and end_dt:
        return _make_result(start_dt, end_dt, "ISO", inherited=False)
    return None


# ── Format 2: US date  "02/03/2026 21:22" ─────────────────────────────────────

def _parse_us_date(start_raw: str, end_raw: str, _alongside=None) -> Optional[dict]:
    patterns = [
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})",   # 02/03/2026 21:22
        r"(\d{2}/\d{2}/\d{4})\s+(\d{4})",           # 02/03/2026 2122
    ]
    start_dt = _try_patterns_us(start_raw, patterns)
    end_dt   = _try_patterns_us(end_raw, patterns)
    if start_dt and end_dt:
        return _make_result(start_dt, end_dt, "US_DATE", inherited=False)
    return None


# ── Format 4: "16:12 hrs. @ 25/11/2025" ──────────────────────────────────────

def _parse_hrs_at(start_raw: str, end_raw: str, _alongside=None) -> Optional[dict]:
    # Matches: "16:12 hrs. @ 25/11/2025" or "16:12 h.s @ 25/11/2025" (OCR variants)
    pattern = r"(\d{1,2}:\d{2})\s*h[rs\.]*s?\.?\s*@\s*(\d{2}/\d{2}/\d{4})"
    start_dt = _try_hrs_at(start_raw, pattern)
    end_dt   = _try_hrs_at(end_raw, pattern)
    if start_dt and end_dt:
        return _make_result(start_dt, end_dt, "HRS_AT", inherited=False)
    return None


# ── Format 3: Time only, inherit date from Alongside line ─────────────────────

def _parse_time_only(start_raw: str, end_raw: str, alongside_raw: Optional[str]) -> Optional[dict]:
    """
    For handwritten BDNs where Commenced/Completed lines have only a time.
    The date is inherited from the "Alongside Vessel" line.
    """
    # Extract anchor date from alongside line
    anchor_date = _extract_alongside_date(alongside_raw) if alongside_raw else None

    if not anchor_date:
        logger.debug("time_only: no anchor date from alongside line '%s'", alongside_raw)
        return None

    start_time = _extract_time_only(start_raw)
    end_time   = _extract_time_only(end_raw)

    if not start_time or not end_time:
        return None

    start_dt = datetime.combine(anchor_date, start_time)
    end_dt   = datetime.combine(anchor_date, end_time)

    return _make_result(start_dt, end_dt, "INHERITED", inherited=True)

def _parse_date_at_hrs(start_raw: str, end_raw: str, _alongside=None) -> Optional[dict]:
    # Handles: "17-11-2025 @ 1000 HRS"
    pattern = r"(\d{2}-\d{2}-\d{4})\s*@\s*(\d{4})\s*HRS"
    start_dt = _try_date_at_hrs(start_raw, pattern)
    end_dt   = _try_date_at_hrs(end_raw, pattern)
    if start_dt and end_dt:
        return _make_result(start_dt, end_dt, "DATE_AT_HRS", inherited=False)
    return None

def _try_date_at_hrs(text: str, pattern: str) -> Optional[datetime]:
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    date_str, time_str = m.group(1), m.group(2)
    time_str = f"{time_str[:2]}:{time_str[2:]}"
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M")
    except ValueError:
        return None

# ── Midnight crossing fix ─────────────────────────────────────────────────────

def _fix_midnight_crossing(result: dict) -> dict:
    """
    If end_dt < start_dt, the delivery crossed midnight.
    Add 1 day to end_dt to fix it.

    Example (Format 3):
        Alongside:  1 MARCH 2026  0025   ← this is the anchor date
        Commenced:  0150                  → 1 MARCH 2026 01:50
        Completed:  0805                  → 1 MARCH 2026 08:05
        No crossing — fine.

    Example (Format 2):
        Commenced:  02/03/2026 21:22     → 2026-03-02 21:22
        Completed:  03/03/2026 02:00     → 2026-03-03 02:00
        Already on separate dates — no fix needed (parser handles this).

    Example (Format 3 with real crossing):
        Alongside:  1 MARCH 2026  2300
        Commenced:  2350
        Completed:  0430                 ← smaller than start = crossed midnight
        Fix:        end_dt = 2 MARCH 2026 04:30
    """
    start_dt = result.get("start_dt")
    end_dt   = result.get("end_dt")

    if not start_dt or not end_dt:
        return result

    crossed = False
    if end_dt < start_dt:
        end_dt = end_dt + timedelta(days=1)
        crossed = True
        logger.debug("Midnight crossing detected — end_dt advanced by 1 day")

    result["end_dt"]          = end_dt
    result["end_str"]         = end_dt.strftime("%Y-%m-%d %H:%M")
    result["crossed_midnight"] = crossed
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(start_dt: datetime, end_dt: datetime, fmt: str, inherited: bool) -> dict:
    return {
        "start_dt":        start_dt,
        "end_dt":          end_dt,
        "start_str":       start_dt.strftime("%Y-%m-%d %H:%M"),
        "end_str":         end_dt.strftime("%Y-%m-%d %H:%M"),
        "crossed_midnight": False,   # updated by _fix_midnight_crossing
        "inherited_date":  inherited,
        "parse_format":    fmt,
        "error":           None,
    }


def _failed(reason: str) -> dict:
    return {
        "start_dt":        None,
        "end_dt":          None,
        "start_str":       None,
        "end_str":         None,
        "crossed_midnight": False,
        "inherited_date":  False,
        "parse_format":    "FAILED",
        "error":           reason,
    }


def _try_patterns(text: str, patterns: list) -> Optional[datetime]:
    """Try regex patterns for ISO-style and abbreviated-month dates.

    Handles:
      "2026-02-03 08:47:15"  → %Y-%m-%d %H:%M
      "11-Feb-2026 18:04:15" → %d-%b-%Y %H:%M
    """
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            date_str, time_str = m.group(1), m.group(2)
            # Normalise time: strip seconds, keep HH:MM
            clean_time = time_str[:5]  # "18:04" from "18:04:15"
            for fmt in ("%Y-%m-%d %H:%M", "%d-%b-%Y %H:%M"):
                try:
                    return datetime.strptime(f"{date_str} {clean_time}", fmt)
                except ValueError:
                    continue
    return None


def _try_patterns_us(text: str, patterns: list) -> Optional[datetime]:
    """Try regex patterns for US-format dates (DD/MM/YYYY)."""
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            date_str, time_str = m.group(1), m.group(2)
            time_str = time_str.replace(":", "")
            if len(time_str) == 4:
                time_str = f"{time_str[:2]}:{time_str[2:]}"
            try:
                return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            except ValueError:
                continue
    return None


def _try_hrs_at(text: str, pattern: str) -> Optional[datetime]:
    """Parse 'HH:MM hrs. @ DD/MM/YYYY' format."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    time_str, date_str = m.group(1), m.group(2)
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def _extract_alongside_date(alongside_raw: str):
    """
    Extract date from "Alongside Vessel" line for Format 3 inheritance.

    Handles:
      "1 MARCH 2026  0025"
      "01/03/2026 0025"
      "2026-03-01 00:25"
    """
    from datetime import date

    # Written month name: "1 MARCH 2026" or "01 MARCH 2026"
    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "JUNE": 6,
        "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10,
        "NOVEMBER": 11, "DECEMBER": 12,
    }
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", alongside_raw)
    if m:
        day, month_name, year = m.group(1), m.group(2).upper(), m.group(3)
        month = months.get(month_name)
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                pass

    # Numeric: DD/MM/YYYY
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", alongside_raw)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # ISO: YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", alongside_raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    return None


def _extract_time_only(text: str):
    """
    Extract time from a string that contains only a time (no date).

    Handles:
      "0150"       → 01:50
      "01:50"      → 01:50
      "0805"       → 08:05
    """
    from datetime import time

    # 4-digit compact: 0150, 0805, 0025
    m = re.search(r"\b(\d{2})(\d{2})\b", text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return time(h, mn)

    # HH:MM
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return time(h, mn)

    return None