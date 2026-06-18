"""
Value normalizer — Phase 2.
Converts extracted raw strings into canonical formats.
All timestamp formats from config.yaml extraction.timestamp_formats.
"""

from __future__ import annotations

import re
from typing import Any

from core.config_loader import get_config


# ── Timestamp normalisation ────────────────────────────────────────────────

_TIME_PATTERNS = [
    # "1 June 2024 14:30"
    (r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+(\d{1,2}):(\d{2})", "%d %B %Y %H:%M"),
    # "2024-06-01T14:30:00"
    (r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", None),
    # "01/06/2024 14:30"
    (r"(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2})", None),
    # "1430 HRS" or "1430"  (time-only, used with anchor date)
    (r"\b(\d{4})\s*(?:HRS|hrs|H)?\b", None),
    # "2:30 PM"
    (r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)", None),
]


_DATE_PATTERN = (
    r"^("
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{4}"
    r"|\d{4}[/\-]\d{2}[/\-]\d{2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
    r")"
)

def normalize_timestamp(raw: str | None) -> str | None:
    """Return timestamp as 'DD Month YYYY HH:MM' string, or raw if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    # Replace all newlines/tabs with space
    normalized_raw = re.sub(r"[\s\r\n]+", " ", raw)
    # Handle compacted dates without separators: '11Feb2026', '11JAN2026'
    compacted = re.match(
        r"(\d{1,2})(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(\d{4})",
        normalized_raw, re.IGNORECASE
    )
    if compacted:
        normalized_raw = f"{compacted.group(1)} {compacted.group(2)} {compacted.group(3)}"

    m = re.match(_DATE_PATTERN, normalized_raw, re.IGNORECASE)
    if m:
        date_part = m.group(1)
        time_raw = normalized_raw[m.end():].strip()
        # Reconstruct time part
        time_digits = re.sub(r"\D", "", time_raw)
        if len(time_digits) == 1:
            time_part = f"0{time_digits}:00"
        elif len(time_digits) == 2:
            time_part = f"{time_digits}:00"
        elif len(time_digits) == 3:
            padded = time_digits.zfill(4)
            time_part = f"{padded[:2]}:{padded[2:]}"
        elif len(time_digits) >= 4:
            time_part = f"{time_digits[:2]}:{time_digits[2:4]}"
        else:
            time_part = "00:00"
        return f"{date_part} {time_part}"
    
    return raw


def normalize_time_only(raw: str | None) -> str | None:
    """Convert '1430', '14:30', '2:30 PM', '1430 HRS' → 'HH:MM'."""
    if not raw:
        return None
    raw = raw.strip()
    # Already HH:MM
    if re.fullmatch(r"\d{2}:\d{2}", raw):
        return raw
    # 4-digit HHMM
    m = re.fullmatch(r"(\d{2})(\d{2})\s*(?:HRS|hrs|H)?", raw)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    # H:MM AM/PM
    m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)", raw)
    if m:
        h, mn, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if period == "PM" and h != 12:
            h += 12
        elif period == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mn:02d}"
    return raw


def normalize_quantity(raw: str | float | None) -> float | None:
    """'1,175.25 MT', '1175.25', '1175' → 1175.25."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[^\d.]", "", str(raw).replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_imo(raw: str | None) -> str | None:
    """Strip non-digits; validate 7-digit format."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits if len(digits) == 7 else None


def normalize_port(raw: str | None) -> str | None:
    """Strip extra whitespace, title-case."""
    if not raw:
        return None
    return " ".join(raw.split()).title()


def normalize_vessel_name(raw: str | None) -> str | None:
    """Strip leading MV/MT/M.V. prefixes and normalize whitespace. Preserves title case."""
    if not raw:
        return None
    cleaned = re.sub(r"^(M\.?V\.?|M\.?T\.?|MV|MT)\s+", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split())
    # Preserve original case if mixed; force title case if all-caps (OCR artifact)
    if cleaned.isupper() and len(cleaned) > 2:
        return cleaned.title()
    return cleaned


def normalize_barge_name(raw: str | None) -> str | None:
    """Remove common prefixes, normalize whitespace, upper case."""
    if not raw:
        return None
    prefixes = get_config().get("barge_verification", {}).get("name_prefixes_to_strip", ["MT ", "MV ", "M/V ", "M/T "])
    name = raw.strip().upper()
    for pfx in prefixes:
        if name.startswith(pfx.upper()):
            name = name[len(pfx):]
            break
    return " ".join(name.split())


def normalize_density(raw: str | float | None) -> float | None:
    """Normalize density: convert from kg/m³ to g/cm³ (divide by 1000 if > 10.0)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
    else:
        cleaned = re.sub(r"[^\d.]", "", str(raw).replace(",", ""))
        try:
            val = float(cleaned)
        except ValueError:
            return None
    if val > 10.0:
        val = val / 1000.0
    return round(val, 4)


def normalize_all(fields: dict[str, Any]) -> dict[str, Any]:
    """Apply all normalizers to an extracted fields dict."""
    out = dict(fields)
    out["vessel_name"] = normalize_vessel_name(fields.get("vessel_name"))
    out["imo"] = normalize_imo(fields.get("imo"))
    out["barge_name"] = normalize_barge_name(fields.get("barge_name"))
    out["port"] = normalize_port(fields.get("port"))
    out["quantity_mt"] = normalize_quantity(fields.get("quantity_mt"))
    out["density"] = normalize_density(fields.get("density"))
    out["start_time"] = normalize_timestamp(fields.get("start_time"))
    out["end_time"] = normalize_timestamp(fields.get("end_time"))
    return out
