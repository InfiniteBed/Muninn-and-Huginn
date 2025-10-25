from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml

__all__ = ["load_global_config", "GLOBAL_CONFIG_PATH", "DEFAULT_GLOBAL_CONFIG"]

GLOBAL_CONFIG_PATH = Path(__file__).resolve().parent / "global_config.yaml"

DEFAULT_GLOBAL_CONFIG: Dict[str, Any] = {
    "plex": {
        "enabled": False,
        "base_url": "http://localhost:32400",
        "token": "YOUR_PLEX_TOKEN",
        "music_library": "Music",
        "allow_transcode": True,
        "timeout": 10,
    },
    "music": {
        "default_provider": "youtube",
    },
}

_config_cache: Dict[str, Any] | None = None

def _merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge configuration dictionaries."""
    merged: Dict[str, Any] = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged

def _ensure_config_file() -> None:
    if not GLOBAL_CONFIG_PATH.exists():
        GLOBAL_CONFIG_PATH.write_text(
            "# Global configuration for Muninn/Huginn bot\n"
            "# Update the Plex section with your server details.\n"
            + yaml.safe_dump(DEFAULT_GLOBAL_CONFIG, sort_keys=False),
            encoding="utf-8",
        )

def load_global_config(*, refresh: bool = False) -> Dict[str, Any]:
    """Load the global configuration, creating the file with defaults if needed."""
    global _config_cache
    _ensure_config_file()

    if _config_cache is None or refresh:
        with GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream) or {}
        _config_cache = _merge_dicts(DEFAULT_GLOBAL_CONFIG, raw)

    return deepcopy(_config_cache)
