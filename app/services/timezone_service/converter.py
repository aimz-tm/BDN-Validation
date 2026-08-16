"""Convert BDN local delivery times to UTC using port timezone lookup."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
import pytz

from app.core.config_loader import get_config

_PORTS: dict[str, Any] | None = None


def _load_ports() -> dict[str, Any]:
    global _PORTS
    if _PORTS is not None:
        return _PORTS
    path = Path(__file__).resolve().parent / "ports.yaml"
    with path.open("r", encoding="utf-8") as f:
        _PORTS = yaml.safe_load(f) or {}
    return _PORTS


def resolve_port(port_name: str | None) -> dict[str, Any]:
    ports = _load_ports()
    if not port_name:
        return ports.get("DEFAULT", {})
    key = port_name.strip()
    if key in ports:
        return ports[key]
    for name, data in ports.items():
        if name.upper() in key.upper() or key.upper() in name.upper():
            return data
    return ports.get("DEFAULT", {})


def _parse_local_datetime(text: str, delivery_date: str | None) -> datetime | None:
    patterns = [
        "%d %B %Y %H:%M",
        "%d %b %Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
    ]
    for fmt in patterns:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    time_match = re.search(r"\d{1,2}:\d{2}", text)
    if delivery_date and time_match:
        combined = f"{delivery_date} {time_match.group()}"
        for fmt in ("%d %B %Y %H:%M", "%d %b %Y %H:%M"):
            try:
                return datetime.strptime(combined, fmt)
            except ValueError:
                continue
    return None


def delivery_window_utc(extraction: dict[str, Any]) -> dict[str, Any]:
    """
    Parse start/end from BDN and return UTC window + port coordinates.
  Never raises.
    """
    port_data = resolve_port(extraction.get("port"))
    tz_name = port_data.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.UTC
        tz_name = "UTC"

    start_local = _parse_local_datetime(
        str(extraction.get("start_time") or ""),
        extraction.get("delivery_date"),
    )
    end_local = _parse_local_datetime(
        str(extraction.get("end_time") or ""),
        extraction.get("delivery_date"),
    )

    if not start_local or not end_local:
        return {
            "start_utc": None,
            "end_utc": None,
            "timezone_normalized": False,
            "port_lat": port_data.get("lat"),
            "port_lon": port_data.get("lon"),
            "timezone": tz_name,
        }

    if start_local >= end_local:
        start_local, end_local = end_local, start_local

    start_utc = tz.localize(start_local).astimezone(timezone.utc)
    end_utc = tz.localize(end_local).astimezone(timezone.utc)

    return {
        "start_utc": start_utc,
        "end_utc": end_utc,
        "timezone_normalized": tz_name != "UTC" or bool(extraction.get("port")),
        "port_lat": port_data.get("lat"),
        "port_lon": port_data.get("lon"),
        "timezone": tz_name,
    }
