"""Configuration management for esp-remote."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

# Default paths
ESP_REMOTE_DIR = Path.home() / ".esp-remote"
CONFIG_FILE = ESP_REMOTE_DIR / "config.toml"
REGISTRY_DIR = ESP_REMOTE_DIR / "registry"
DEVICES_FILE = REGISTRY_DIR / "devices.toml"


def ensure_dirs():
    """Create necessary directories."""
    ESP_REMOTE_DIR.mkdir(exist_ok=True)
    REGISTRY_DIR.mkdir(exist_ok=True)


def load_config() -> dict:
    """Load local config."""
    if CONFIG_FILE.exists():
        return tomllib.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    """Save local config."""
    ensure_dirs()
    CONFIG_FILE.write_bytes(tomli_w.dumps(config).encode())


def load_devices() -> dict:
    """Load device registry."""
    if DEVICES_FILE.exists():
        return tomllib.loads(DEVICES_FILE.read_text())
    return {"device": {}}


def save_devices(devices: dict):
    """Save device registry."""
    ensure_dirs()
    DEVICES_FILE.write_bytes(tomli_w.dumps(devices).encode())
