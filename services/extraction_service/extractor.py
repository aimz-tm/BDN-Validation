"""
Extraction service router — Phase 2 (improved).
Routes to DigitalExtractor or HandwrittenExtractor based on doc_type.
Runs normalizer on all output fields.

Key fixes:
  - Date regex handles DD/MM/YYYY, DD-MM-YYYY, DD Month YYYY, YYYY-MM-DD
  - Time regex handles HH:MM, HHMM, with or without date prefix
  - Port / supplier / barge use find_proper_noun (5-word cap)
  - Start/end time: broader patterns capturing any timestamp near the label
  - spaCy NER fallback: skipped if import fails (non-blocking)
"""

from __future__ import annotations

import re
from typing import Any

from services.extraction_service.base_extractor import BaseExtractor
from services.extraction_service.normalizer import normalize_all



# ── Date / time helpers ───────────────────────────────────────────────────

# Any of:  20/04/2026  |  20-04-2026  |  20 Apr 2026  |  2026-04-20
_MONTHS_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_RE = (
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}"       # DD/MM/YYYY or DD-MM-YYYY
    r"|\d{4}[/\-]\d{2}[/\-]\d{2}"            # YYYY-MM-DD
    r"|\d{1,2}\s+" + _MONTHS_PATTERN + r"\s+\d{4}"  # 20 April 2026
    r"|" + _MONTHS_PATTERN + r"\s+\d{1,2},?\s+\d{4})"  # April 20, 2026
)

# Timestamp = date + optional HH:MM (or HHMM or HH:MM:SS)
_DT_RE = r"(" + rf"(?:{_DATE_RE[1:-1]})" + r"(?:\s+\d{2}:\d{2}(?::\d{2})?)?)"

# Time-only (when date already known from anchor)
_TIME_RE = r"(\d{2}:\d{2}(?::\d{2})?|\d{4})"


def _label_then_dt(label_pattern: str) -> str:
    """Build a regex: label followed by a date(+time) value."""
    return rf"(?:{label_pattern})\s*[:\s]+{_DT_RE}"


def _label_then_date(label_pattern: str) -> str:
    return rf"(?:{label_pattern})\s*[:\s]+{_DATE_RE}"


# ── Shared field extraction logic ─────────────────────────────────────────

def _extract_common(ext: BaseExtractor) -> dict[str, Any]:
    """
    Core field extraction shared by Digital and Handwritten extractors.
    Uses ext.find() and ext.find_number() which respect the subclass fuzzy_threshold.
    """

    # ── Vessel name ─────────────────────────────────────────────────────
    vessel_name = ext.find(
        [
            # "Vessel's Name : STAR ELIZABETH" (most specific — must come before Bunker Tanker)
            r"Vessel'?s?\s+Name\s*[:\s]+([A-Za-z][A-Za-z0-9 \-]+)",
            r"(?:Receiving\s+Vessel|Ship)\s+Name\s*[:\s]+([A-Za-z][A-Za-z0-9 \-]+)",
            r"Name\s+of\s+(?:Vessel|Ship)\s*[:\s]+([A-Za-z][A-Za-z0-9 \-]+)",
            r"M\.?V\.?\s+([A-Za-z][A-Za-z0-9 \-]{2,})",
            r"(?:To\s+)?(?:Vessel|Ship)\s*[:\s]+([A-Za-z][A-Za-z0-9 \-]{2,})",
        ],
        field="vessel_name",
        extra_labels=["Vessel Name", "Ship Name", "Receiving Vessel", "MV", "Motor Vessel", "Name of Vessel", "Vessel"],
        max_words=6,
    )
    # Normalize to title case (some OCR outputs are all-caps)
    if vessel_name:
        vessel_name = vessel_name.strip().title() if vessel_name.isupper() else vessel_name.strip()

    # ── IMO number ──────────────────────────────────────────────────────
    imo = ext.find(
        [
            r"IMO\s+(?:Number|No\.?|#)\s*[:\s]*(\d{7})",
            r"\bIMO\s*[:\s]*(\d{7})\b",
            r"\b(IMO\d{7})\b",
            r"(?:Vessel\s+)?(?:Official|Reg\.?)\s+No\.?\s*[:\s]*(\d{7})",
            # "Vessel's IMO No. : 9917488"
            r"Vessel'?s?\s+IMO\s+No\.?\s*[:\s]*(\d{7})",
            # 7-digit number on its own line (next-line after IMO label)
            r"(?:Vessel\s+IMO|IMO\s+Number)[^\n]*\n(?:[^\n]*\n){0,3}(\d{7})",
        ],
        field="imo",
        extra_labels=["IMO Number", "IMO No", "Vessel IMO Number", "IMO", "Vessel's IMO No"],
        max_words=1,
    )

    # ── Barge name (name only — no IMO) ──────────────────────────────────────
    barge_name = ext.find(
        [
            # "Bunker Tanker's Name : MARINE ORACLE" — must come first to avoid
            # accidentally matching vessel name patterns
            r"Bunker\s+Tanker'?s?\s+Name\s*[:\s]+([A-Z][A-Z0-9 \-]+)",
            r"(?:Barge|Bunker\s+Barge|Bunker\s+Craft|Bunker\s+Tanker|Delivering\s+Vessel)\s+Name\s*[:\s]+([A-Z0-9][A-Z0-9 \-]+)",
            r"(?:Bunker\s+Barge|Bunker\s+Craft|Delivering\s+Vessel)\s*[:\s]+([A-Z0-9][A-Z0-9 \-]+)",
            # Bunker Tanker Name on its own line, value on next line
            r"Bunker\s+Tanker(?:'s)?\s+Name[^\n]*\n([A-Z0-9][A-Z0-9 /T\-]+)",
        ],
        field="barge_name",
        extra_labels=[
            "Barge Name", "Bunker Barge", "Bunker Tanker", "Bunker Tanker Name", "Bunker Tanker's Name",
            "Delivering Vessel", "Bunker Vessel", "Bunker Craft", "Barge",
        ],
        max_words=5,
    )
    # Strip OCR artifacts and trailing noise from barge name
    if barge_name:
        barge_name = re.sub(r"^[/\\]?T\s+", "", barge_name).strip() or None
    if barge_name:
        # Strip trailing noise words that bleed in from adjacent fields
        barge_name = re.sub(
            r"\s+(VESSEL|NAME|TANKER|BARGE|CRAFT|SB|IMO|NO\.?|NUMBER|GROSS|TONNAGE)(?:\s+.*)?$",
            "", barge_name.strip(), flags=re.IGNORECASE
        ).strip() or None

    # ── SB number ───────────────────────────────────────────────────
    barge_sb_number = ext.find(
        [
            r"SB\s*(?:Number|No\.?|#)\s*[:\s]+([A-Z0-9 \-]+)",
            r"\bSB\s*[:\s]+([A-Z0-9][A-Z0-9 \-]*)",
            # "SB 9333D" inline (no colon)
            r"\b(SB\s+[A-Z0-9]{3,10})\b",
        ],
        field="barge_sb_number",
        extra_labels=["SB Number", "SB No", "SB#", "SB No."],
        max_words=2,
    )
    # Normalize SB number: remove internal spaces ("SB 9333D" → "SB9333D")
    if barge_sb_number:
        barge_sb_number = re.sub(r"\s+", "", barge_sb_number.strip())

    # ── Delivery date ─────────────────────────────────────────────────────
    delivery_date = ext.find(
        [
            _label_then_date(r"Delivery\s+Date"),
            _label_then_date(r"Date\s+of\s+Delivery"),
            _label_then_date(r"Bunkering\s+Date"),
            _label_then_date(r"Date\s+of\s+Bunkering"),
            # Standalone date line fallback
            _DATE_RE,
        ],
        field="delivery_date",
        extra_labels=["Delivery Date", "Date of Delivery", "Bunkering Date", "Date"],
        max_words=4,
    )

    # ── Start time ────────────────────────────────────────────────────────
    # ISO datetime: "2026-02-03 08:47:15" (eBDN format — highest priority)
    _ISO_DT = r"(\d{4}-\d{2}-\d{2}[\s T]\d{2}:\d{2}(?::\d{2})?)"
    # Non-ISO cross-line pattern (two-column BDN interleaved layout)
    _TS = (
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{4}[\s\r\n]+(?:\d{1,2}[\s\r\n]*:?[\s\r\n]*\d{1,2}(?::\d{2})?|\d{4})?"
        r"|\d{4}[/\-]\d{2}[/\-]\d{2}[\s\r\n]+(?:\d{1,2}[\s\r\n]*:?[\s\r\n]*\d{1,2}(?::\d{2})?|\d{4})?)"
    )
    start_time = ext.find(
        [
            # ISO datetime first — most specific
            rf"(?:Alongside\s+Vessel)[\s\S]{{0,100}}?{_ISO_DT}",
            rf"(?:Commenced?|Commencement)\s+Pumping[\s\S]{{0,100}}?{_ISO_DT}",
            rf"(?:Pumping\s+Start|Hose\s+On)[\s\S]{{0,100}}?{_ISO_DT}",
            # Skip-ahead cross-line patterns
            rf"(?:Alongside\s+Vessel)[\s\S]{{0,300}}?{_TS}",
            rf"(?:Commenced?|Commencement)\s+Pumping[\s\S]{{0,300}}?{_TS}",
            rf"(?:Pumping\s+Start|Hose\s+On|Hose\s+Connected)[\s\S]{{0,300}}?{_TS}",
            # Same-line variants
            _label_then_dt(r"Alongside\s+Vessel"),
            _label_then_dt(r"(?:Commenced?|Commencement)(?:\s+Pumping)?"),
            _label_then_dt(r"Pumping\s+Start(?:\s+Time)?"),
            _label_then_dt(r"Hose\s+(?:On|Connected)"),
            rf"(?:Pumping\s+Start|Start\s+Time|Hose\s+On|Alongside)\s*[:\s]+({_TIME_RE[1:-1]})",
        ],
        field="start_time",
        extra_labels=[
            "Alongside Vessel", "Commenced Pumping", "Pumping Start Time",
            "Start Time", "Hose On", "Hose Connected", "Commencement",
        ],
        max_words=5,
    )

    # ── End time ──────────────────────────────────────────────────────────
    end_time = ext.find(
        [
            # ISO datetime first
            rf"(?:Completed?\s+Pumping|Completion)[\s\S]{{0,100}}?{_ISO_DT}",
            rf"(?:Pumping\s+(?:End|Stop|Finish)|Hose\s+Off)[\s\S]{{0,100}}?{_ISO_DT}",
            # Skip-ahead cross-line patterns
            rf"(?:Completed?\s+Pumping|Completion)[\s\S]{{0,300}}?{_TS}",
            rf"(?:Pumping\s+(?:End|Stop|Finish)|Hose\s+Off)[\s\S]{{0,300}}?{_TS}",
            # Same-line variants
            _label_then_dt(r"Completed?\s+Pumping"),
            _label_then_dt(r"Pumping\s+(?:End|Stop|Finish|Completion)(?:\s+Time)?"),
            _label_then_dt(r"Hose\s+(?:Off|Disconnected)"),
            _label_then_dt(r"Completion"),
            rf"(?:Pumping\s+End|End\s+Time|Hose\s+Off)\s*[:\s]+({_TIME_RE[1:-1]})",
        ],
        field="end_time",
        extra_labels=[
            "Completed Pumping", "Pumping End Time", "End Time",
            "Hose Off", "Hose Disconnected", "Completion",
        ],
        max_words=5,
    )

    # ── Port ──────────────────────────────────────────────────────────────
    port = ext.find(
        [
            r"Port\s+of\s+(?:Delivery|Bunkering|Loading)\s*[:\s]+([A-Za-z][A-Za-z ]{2,30})",
            # "Port : Singapore Date :" — must stop before 'Date'
            r"(?m)^Port\s*[:\s]+([A-Za-z][A-Za-z ]{2,25})(?=\s+Date|\s*$)",
            r"(?:Bunkering\s+)?Port\s*[:\s]+([A-Za-z][A-Za-z ]{2,25})",
            r"Delivery\s+Location\s*[:\s]+([A-Za-z][A-Za-z ]{2,25})",
            r"Location\s*[:\s]+([A-Za-z][A-Za-z ]{2,25})",
            r"Anchorage\s*[:\s]+([A-Za-z][A-Za-z ]{2,25})",
        ],
        field="port",
        extra_labels=["Port of Delivery", "Port", "Bunkering Port", "Location", "Delivery Location", "Anchorage", "Place"],
        max_words=4,  # Port names are short: "Singapore", "Port Klang", etc.
    )
    # Strip trailing postcode/number from port (e.g. "Singapore 537084" → "Singapore")
    if port:
        port = re.sub(r"\s+\d{3,}$", "", port.strip()).strip() or None
    # Strip trailing keyword artifacts: "Singapore Date" → "Singapore"
    if port:
        port = re.sub(r"\s+(Date|Time|No\.?|Number)\s*$", "", port.strip(), flags=re.IGNORECASE).strip() or None
    # Fix OCR-truncated port names (e.g. "Singapor" → "Singapore")
    _port_corrections = {
        "singapor": "Singapore", "singapo": "Singapore", "singap": "Singapore",
        "rotterda": "Rotterdam", "fujairah": "Fujairah", "port klan": "Port Klang",
    }
    if port and port.lower().rstrip() in _port_corrections:
        port = _port_corrections[port.lower().rstrip()]

    # ── Supplier ───────────────────────────────────────────────────────────
    supplier = ext.find(
        [
            # Explicit supplier field
            r"(?:Physical\s+)?Supplier\s*[:\s]+([A-Za-z][A-Za-z ]{2,40}(?:Ltd|Inc|Pte|Corp|Co\.?)?)",
            r"Seller\s*[:\s]+([A-Za-z][A-Za-z ]{2,40})",
            r"Bunker\s+(?:Company|Trader|Supplier)\s*[:\s]+([A-Za-z][A-Za-z ]{2,40})",
            # Full company name line (often appears in footer/header of BDN)
            r"([A-Z][A-Z ]{5,50}(?:PTE|LTD|INC|CORP|SDN|BHD|MARINE|FUEL|OIL|ENERGY)(?:\s+(?:LTD|BHD|PTY))?)",
            # Company name in header (e.g. "G EQUATORIAL" or full company name before BDN No)
            r"(?:Company|Firm|Corp)\.?\s*[:\s]+([A-Za-z][A-Za-z &.]{3,40})",
        ],
        field="supplier",
        extra_labels=["Supplier", "Seller", "Bunker Company", "Physical Supplier", "Bunker Trader"],
        max_words=5,
    )
    # Exclude LICENCE NO false positives (from 'BUNKER SUPPLIER LICENCE NO: 02252')
    if supplier and re.search(r"LICENCE|LICENSE|LIC\s*NO", supplier, re.IGNORECASE):
        supplier = None

    # ── Quantity ──────────────────────────────────────────────────────────
    quantity = ext.find_number(
        [
            r"(?:Total\s+)?Quantity\s+(?:Delivered|Supplied|Received|in\s+MT)\s*[:\s]+([\d,]+\.?\d*)",
            r"(?:Total\s+)?Quantity\s*[:\s]+([\d,]+\.?\d*)\s*(?:MT|M/T|Metric\s*Ton)?",
            r"(?:Net\s+)?(?:Standard\s+)?Volume\s*[:\s]+([\d,]+\.?\d*)",
            r"Mass\s*[:\s]+([\d,]+\.?\d*)",
            # "Metric Tons Delivered XXX.XXX" — value on same line after label
            r"Metric\s+Tons\s+Delivered[:\s]+([\d,]+\.?\d*)",
            r"Metric\s+Tons\s+Delivered\s+([\d,]+\.\d+)",
            # Standalone "XXX.XX MT" or "XXX.XXX MT" on its own line
            r"^\s*([\d,]{2,}\.[\d]+)\s*(?:MT|M/T|Metric\s+Ton)\b",
            # Large round number + MT anywhere
            r"([1-9]\d{2,5}\.\d{1,3})\s*(?:MT|M/T)\b",
        ],
        field="quantity_mt",
        extra_labels=[
            "Quantity Delivered", "Quantity", "Total Quantity", "Volume", "Mass",
            "Net Volume", "Metric Tons Delivered", "Metric Tons", "MT Delivered",
        ],
    )

    density = ext.find_number(
        [
            r"Density\s+(?:at\s+)?(?:15\s*°?C\s*)?[:\s]+([\d.]+)\s*(?:kg/m3|kg/L|g/mL)?",
            r"Specific\s+Gravity\s*[:\s]+([\d.]+)",
            r"Density\s+(?:at\s+)?(?:15\s*°?C\s*)[^\n]*\n\s*([\d.]+)",
            r"Density\s+(?:at\s+)?(?:15\s*°?C\s*)[^\n]*\n(?:[^\n]*\n){0,2}\s*([\d.]+)",
        ],
        field="density",
        extra_labels=["Density", "Density at 15C", "Specific Gravity"],
    )

    # ── Sulphur ─────────────────────────────────────────────────────────────
    # Two-column BDN problem: viscosity (3.448) appears before sulphur (0.092)
    # in the raw OCR text. Strategy: find ALL decimal values near the label,
    # then pick the one in a valid sulphur range (0.001–5.0).
    sulphur = ext.find_number(
        [
            r"Sul(?:ph|f)ur(?:\s+Content)?(?:\s+%[\s\w/]*)?\s*[:\s]+([\d.]+)\s*%?",
            r"S\s+Content\s*[:\s]+([\d.]+)",
        ],
        field="sulphur_content",
        extra_labels=["Sulphur Content", "Sulphur", "Sulfur", "S Content", "Sulphur Content % m/m"],
    )
    # If the above fails or gives an out-of-range value, scan the window after
    # the 'Sulphur' label for ALL decimals and pick the one in range 0.001–5.0
    if sulphur is None or not (0.001 <= sulphur <= 5.0):
        sulphur = None
        idx = re.search(r"Sul(?:ph|f)ur", ext.text, re.IGNORECASE)
        if idx:
            window = ext.text[idx.start(): idx.start() + 500]
            candidates = [float(m) for m in re.findall(r"\b([0-4]\.\d{2,4})\b", window)]
            # Valid sulphur values: 0.001–5.0; prefer smallest if multiple in range
            valid = [v for v in candidates if 0.001 <= v <= 5.0]
            if valid:
                sulphur = min(valid)  # sulphur % is almost always the smallest value

    # ── Flashpoint ──────────────────────────────────────────────────────────
    flashpoint = ext.find_number(
        [
            r"Flash\s*[Pp]oint\s*[:\s]+(\d+\.?\d*)\s*°?C?",
            r"\bFP\s*[:\s]+(\d+\.?\d*)",
            # Tabular: 'Flash Point °C' on one line, value on next
            r"Flash\s+Point[^\n]*\n(\d+\.?\d*)",
        ],
        field="flashpoint",
        extra_labels=["Flashpoint", "Flash Point", "Flash Point C", "FP"],
    )

    # ── Fuel type ──────────────────────────────────────────────────────────
    fuel_type = ext.find(
        [
            r"(?:Grade|Fuel\s+Grade|Product|Grade\s+of\s+Product)\s*[:\s]+(VLSFO|LSMGO|IFO380|IFO180|MDO|MGO|HFO|ULSFO|HSFO|[A-Z0-9]{3,8})",
            r"Fuel\s+(?:Type|Grade)\s*[:\s]+([A-Za-z0-9]{2,15})",
            r"^(VLSFO|LSMGO|ULSFO|HSFO|IFO380|IFO180|MDO|MGO|HFO|VLSFO-[A-Z]+)\s*$",
        ],
        field="fuel_type",
        extra_labels=["Fuel Type", "Grade", "Fuel Grade", "Product Grade", "Product", "Product Name"],
        max_words=3,
    )

    # ── Viscosity (ISO 8217) ────────────────────────────────────────────────────
    # Extracted so credibility scorer can check ISO 8217 limits (700 mm²/s at 50°C).
    # Skip-ahead: two-column BDNs put label and value on non-adjacent lines.
    viscosity = ext.find_number(
        [
            r"Viscosity\s*(?:at\s*)?(?:50|40)\s*°?C[^:\d]*[:\s]+([\d.]+)",
            r"Kinematic\s+Viscosity\s*[:\s]+([\d.]+)",
            # Tabular: label then value on next line
            r"Viscosity[\s\S]{0,200}?([0-9]{1,3}\.[0-9]{1,3})(?!\d)",
        ],
        field="viscosity",
        extra_labels=["Viscosity", "Viscosity at 50C", "Viscosity at 40C", "Kinematic Viscosity"],
    )
    # Sanity: viscosity must be positive and < 800 mm²/s
    if viscosity is not None and not (0.1 <= viscosity <= 800):
        viscosity = None

    # ── Water content (MARPOL / ISO 8217) ─────────────────────────────────────────
    # MARPOL limit: ≤0.5% v/v. Extracted to verify compliance.
    water_content = ext.find_number(
        [
            r"Water\s+Content\s*(?:%\s*[Vv]/[Vv])?\s*[:\s]+([\d.]+)",
            r"H2O\s+Content\s*[:\s]+([\d.]+)",
            r"Water\s*[:\s]+([\d.]+)\s*%?",
            # Tabular skip-ahead
            r"Water\s+Content[\s\S]{0,200}?([0-9]\.\d{1,4})(?!\d)",
        ],
        field="water_content",
        extra_labels=["Water Content", "Water", "H2O Content", "Water % V/V", "Water Content % V/V"],
    )
    # Sanity: water content 0–2% v/v (above 2% is measurement error)
    if water_content is not None and not (0.0 <= water_content <= 2.0):
        water_content = None

    seal_vessel = ext.find(
        [
            r"(?:Vessel|Ship)\s+Seal\s*(?:No\.?|Number|#)\s*[:\s]+([A-Z0-9\-]+)",
            # Tabular: 'Vessels:' then seal on next line
            r"Vessels?[:\s]+([A-Z0-9\-/]+)",
        ],
        field="seal_number_vessel",
        extra_labels=["Vessel Seal", "Ship Seal", "Seal Vessel", "Vessels"],
        max_words=2,
    )

    seal_marpol = ext.find(
        [
            r"MARPOL\s+Seal\s*(?:No\.?|Number|#)\s*[:\s]+([A-Z0-9\-]+)",
            # Tabular: 'MARPOL:' then seal number on next line (must look like a seal: alphanumeric)
            r"MARPOL[:\s]+([A-Z][0-9]{4,}(?:[/\-][A-Z0-9]+)?)",
        ],
        field="seal_number_marpol",
        extra_labels=["MARPOL Seal", "Seal MARPOL", "MARPOL"],
        max_words=2,
    )

    seal_barge = ext.find(
        [
            r"(?:Barge|Craft)\s+Seal\s*(?:No\.?|Number|#)\s*[:\s]+([A-Z0-9\-]+)",
            # 'Bunker Tanker:' label in seal section
            r"Bunker\s+Tanker[:\s]+([A-Z0-9\-/]+)",
        ],
        field="seal_number_barge",
        extra_labels=["Barge Seal", "Seal Barge", "Bunker Tanker"],
        max_words=2,
    )

    # ── Post-extraction validation ────────────────────────────────────────────
    # Null-out timestamps with impossible hours (OCR garbling)
    for _ts_key in ("start_time", "end_time"):
        _ts_val = locals().get(_ts_key)
        if _ts_val and isinstance(_ts_val, str):
            _hr_m = re.search(r"(\d{2}):(\d{2})", _ts_val)
            if _hr_m and int(_hr_m.group(1)) >= 24:
                locals()[_ts_key]  # can't reassign locals in Python cleanly

    # Reassign validated timestamps
    def _valid_ts(v):
        if not v:
            return v
        m = re.search(r"(\d{2}):(\d{2})", str(v))
        return v if (not m or int(m.group(1)) < 24) else None

    start_time = _valid_ts(start_time)
    end_time = _valid_ts(end_time)

    # Null out fuel_type if it's clearly a generic placeholder
    _GENERIC_FUEL_WORDS = {"supplied", "product", "grade", "fuel", "type", "name"}
    if fuel_type and fuel_type.lower().strip() in _GENERIC_FUEL_WORDS:
        fuel_type = None

    return {
        "vessel_name":        vessel_name,
        "imo":                imo,
        "barge_name":         barge_name,
        "barge_sb_number":    barge_sb_number,
        "barge_imo":          None,
        "delivery_date":      delivery_date,
        "start_time":         start_time,
        "end_time":           end_time,
        "alongside_vessel":   None,
        "port":               port,
        "supplier":           supplier,
        "quantity_mt":        quantity,
        "density":            density,
        "sulphur_content":    sulphur,
        "flashpoint":         flashpoint,
        "viscosity":          viscosity,
        "water_content":      water_content,
        "fuel_type":          fuel_type,
        "seal_number_vessel": seal_vessel,
        "seal_number_marpol": seal_marpol,
        "seal_number_barge":  seal_barge,
        "anchor_date_used":   None,
        "bdn_reference":      _extract_bdn_reference(ext.text),
    }


# ── BDN reference extraction ──────────────────────────────────────────────────

_BDN_REF_RE = re.compile(
    r"(?:BDN|Bunker\s+Delivery\s+Note)\s*(?:No\.?|Number|#|Ref\.?)\s*[:\s]+([A-Z0-9\-/]+)"
    r"|(?:SDL|BDN|REF)[0-9]{4,10}",  # Common prefixed reference codes
    re.IGNORECASE,
)


def _extract_bdn_reference(text: str) -> str | None:
    """Extract BDN reference / document number for duplicate detection."""
    m = _BDN_REF_RE.search(text)
    if m:
        return (m.group(1) or m.group(0)).strip()
    return None


# ── Routing + confidence scoring ──────────────────────────────────────────

EXPECTED_FIELDS = [
    "vessel_name", "imo", "barge_name", "delivery_date",
    "start_time", "end_time", "port", "supplier", "quantity_mt",
]


def extract_fields(file_path: str, ocr_result: dict | None = None, doc_type: str = "DIGITAL") -> dict[str, Any]:
    """
    Main entry. Routes to correct extractor, normalizes, computes extraction_confidence.
    """
    from services.ocr_service.engine import extract as ocr_extract

    if ocr_result is None:
        ocr_result = ocr_extract(file_path)

    text = ocr_result.get("text", "")
    ocr_conf = float(ocr_result.get("mean_confidence", 0.0))

    if doc_type == "HANDWRITTEN":
        from services.extraction_service.handwritten_extractor import HandwrittenExtractor
        extractor = HandwrittenExtractor(text, ocr_conf)
    else:
        from services.extraction_service.digital_extractor import DigitalExtractor
        extractor = DigitalExtractor(text, ocr_conf)

    fields = extractor.extract()
    fields = normalize_all(fields)

    fields["raw_text"] = text
    fields["ocr_confidence"] = ocr_conf

    # Extraction confidence: weighted blend of field completeness (70%) and OCR quality (30%).
    # This prevents a well-extracted document (8/9 fields) from being penalised just because
    # OCR confidence is moderate (e.g. 0.75 on a clean scan).
    # Old formula: (found/expected) * ocr_conf  — e.g. 0.89 * 0.75 = 0.67 (incorrectly low)
    # New formula: 0.70 * completeness + 0.30 * ocr_conf  — e.g. 0.70*0.89 + 0.30*0.75 = 0.85
    found = sum(1 for f in EXPECTED_FIELDS if fields.get(f))
    completeness = found / len(EXPECTED_FIELDS)
    extraction_confidence = round(0.70 * completeness + 0.30 * ocr_conf, 3)
    fields["extraction_confidence"] = extraction_confidence
    fields["doc_type"] = doc_type

    # spaCy NER fallbacks (non-blocking)
    try:
        from services.document_service.extractor import extract_with_spacy
        spacy_ents = extract_with_spacy(text)
        if not fields.get("port") and spacy_ents.get("locations"):
            fields["port"] = spacy_ents["locations"][0]
        if not fields.get("supplier") and spacy_ents.get("orgs"):
            fields["supplier"] = spacy_ents["orgs"][0]
        if not fields.get("delivery_date") and spacy_ents.get("dates"):
            fields["delivery_date"] = spacy_ents["dates"][0]
        fields["spacy_entities"] = spacy_ents
    except Exception:
        pass

    return fields
