"""Central configuration loader — single source of truth for config.yaml."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
_config: dict[str, Any] | None = None


def _load_from_disk() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a YAML mapping at the root")
    return data


def get_config() -> dict[str, Any]:
    """Return a deep copy so callers cannot mutate the cached singleton."""
    global _config
    if _config is None:
        _config = _load_from_disk()
    return copy.deepcopy(_config)


def reload_config() -> dict[str, Any]:
    """Reload config from disk and return the new snapshot."""
    global _config
    _config = _load_from_disk()
    return copy.deepcopy(_config)


def save_config(updates: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge updates into config.yaml and persist.
    Creates config.yaml.bak before writing.
    """
    global _config
    current = _load_from_disk()
    merged = _deep_merge(current, updates)
    backup = _CONFIG_PATH.with_suffix(".yaml.bak")
    shutil.copy2(_CONFIG_PATH, backup)
    with _CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, default_flow_style=False, sort_keys=False)
    _config = merged
    return copy.deepcopy(_config)


def config_path() -> Path:
    return _CONFIG_PATH


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
