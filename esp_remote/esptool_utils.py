"""esptool utilities for chip detection."""

import re
from dataclasses import dataclass
from typing import Optional

from .ssh import SSHConnection


@dataclass
class ChipInfo:
    """ESP chip information."""
    chip_type: str
    chip_id: str
    mac: str
    device: str


def detect_chip_remote(ssh: SSHConnection, device: str) -> Optional[ChipInfo]:
    """Detect ESP chip on remote device using esptool."""
    # Try to get chip info via esptool (try ~/.local/bin first, then PATH)
    out, err, code = ssh.run(
        f"~/.local/bin/esptool --port {device} --no-stub chip-id 2>&1 || "
        f"esptool --port {device} --no-stub chip-id 2>&1"
    )

    if code != 0:
        # esptool might not be installed
        if "command not found" in err or "command not found" in out or "No such file" in out:
            # Try installing esptool
            ssh.run("pip install esptool --break-system-packages 2>/dev/null || pip install esptool")
            out, err, code = ssh.run(
                f"~/.local/bin/esptool --port {device} --no-stub chip-id 2>&1"
            )

    if code != 0:
        return None

    # Parse output
    chip_type = ""
    chip_id = ""
    mac = ""

    for line in out.split("\n"):
        if "Chip is" in line or "Chip type:" in line:
            match = re.search(r"(?:Chip is|Chip type:)\s*(\S+)", line)
            if match:
                chip_type = match.group(1)
        elif "Chip ID:" in line:
            match = re.search(r"Chip ID: (0x[0-9a-fA-F]+)", line)
            if match:
                chip_id = match.group(1)
        elif "MAC:" in line and not mac:  # Take first MAC only
            match = re.search(r"MAC:\s+([0-9a-fA-F:]+)", line)
            if match:
                mac = match.group(1)

    if chip_id or mac:
        return ChipInfo(
            chip_type=chip_type,
            chip_id=chip_id,
            mac=mac,
            device=device,
        )
    return None


def scan_devices_remote(ssh: SSHConnection) -> list[tuple[str, Optional[ChipInfo]]]:
    """Scan all serial devices on remote host."""
    # Find serial devices
    out, err, code = ssh.run(
        "ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>/dev/null"
    )

    devices = [d.strip() for d in out.split() if d.strip()]
    results = []

    for device in devices:
        chip_info = detect_chip_remote(ssh, device)
        results.append((device, chip_info))

    return results


def verify_chip_id(ssh: SSHConnection, device: str, expected_id: str) -> tuple[bool, str]:
    """Verify chip ID or MAC matches expected."""
    chip_info = detect_chip_remote(ssh, device)

    if not chip_info:
        return False, "Could not read chip info"

    # Check chip_id first, then MAC
    actual_id = chip_info.chip_id or chip_info.mac
    if not actual_id:
        return False, "No chip ID or MAC found"

    if actual_id.lower() == expected_id.lower():
        return True, f"Verified: {actual_id}"

    # Also try matching just the chip_id or just the MAC
    if chip_info.chip_id and chip_info.chip_id.lower() == expected_id.lower():
        return True, f"Chip ID verified: {chip_info.chip_id}"
    if chip_info.mac and chip_info.mac.lower() == expected_id.lower():
        return True, f"MAC verified: {chip_info.mac}"

    return False, f"Mismatch: expected {expected_id}, got {actual_id}"
