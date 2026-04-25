"""
VEGA AI — Configuration Manager
Loads settings from YAML with environment variable overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Any

_CONFIG_CACHE: dict = {}
CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


def load_config(path: str | Path | None = None) -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE:
        return _CONFIG_CACHE
    
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Apply environment variable overrides
    # Format: VEGA_SECTION_KEY=value  (e.g., VEGA_MODELS_DEFAULT_CLOUD=gpt-4o)
    for key, value in os.environ.items():
        if key.startswith("VEGA_"):
            parts = key[5:].lower().split("_", 1)
            if len(parts) == 2 and parts[0] in config:
                section, subkey = parts
                if isinstance(config[section], dict):
                    config[section][subkey] = _cast_value(value)
    
    _CONFIG_CACHE = config
    return config


def get(key_path: str, default: Any = None) -> Any:
    """Get a nested config value using dot notation: 'models.default_cloud'"""
    config = load_config()
    keys = key_path.split(".")
    current = config
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def reload_config():
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    return load_config()


def _cast_value(value: str) -> Any:
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value
