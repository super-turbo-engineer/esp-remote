"""Device registry management."""

from dataclasses import dataclass
from typing import Optional

from .config import load_devices, save_devices


@dataclass
class Device:
    """Registered ESP device."""
    name: str
    chip_id: str
    host: str
    usb_path: str
    remote_port: int
    local_port: int
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "chip_id": self.chip_id,
            "host": self.host,
            "usb_path": self.usb_path,
            "remote_port": self.remote_port,
            "local_port": self.local_port,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Device":
        return cls(
            name=name,
            chip_id=data.get("chip_id", ""),
            host=data.get("host", ""),
            usb_path=data.get("usb_path", ""),
            remote_port=data.get("remote_port", 4000),
            local_port=data.get("local_port", 4000),
            description=data.get("description", ""),
        )


class Registry:
    """Device registry operations."""

    def __init__(self):
        self._data = load_devices()

    def reload(self):
        """Reload from disk."""
        self._data = load_devices()

    def save(self):
        """Save to disk."""
        save_devices(self._data)

    def list_devices(self) -> list[Device]:
        """Get all registered devices."""
        devices = []
        for name, data in self._data.get("device", {}).items():
            devices.append(Device.from_dict(name, data))
        return devices

    def get_device(self, name: str) -> Optional[Device]:
        """Get device by name."""
        data = self._data.get("device", {}).get(name)
        if data:
            return Device.from_dict(name, data)
        return None

    def get_devices_by_host(self, host: str) -> list[Device]:
        """Get all devices on a host."""
        return [d for d in self.list_devices() if d.host == host]

    def add_device(self, device: Device):
        """Add or update a device."""
        if "device" not in self._data:
            self._data["device"] = {}
        self._data["device"][device.name] = device.to_dict()
        self.save()

    def remove_device(self, name: str) -> bool:
        """Remove a device."""
        if name in self._data.get("device", {}):
            del self._data["device"][name]
            self.save()
            return True
        return False

    def next_port(self, host: str, base: int = 4000) -> int:
        """Get next available port for a host."""
        used = {d.remote_port for d in self.get_devices_by_host(host)}
        port = base
        while port in used:
            port += 1
        return port
