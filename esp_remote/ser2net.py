"""ser2net configuration management."""

from typing import Optional

from .registry import Device, Registry
from .ssh import SSHConnection


def generate_config(devices: list[Device], baud: int = 115200) -> str:
    """Generate ser2net.yaml config for devices."""
    lines = ["%YAML 1.1", "---"]

    for i, device in enumerate(devices):
        # Use symlink if usb_path is set (udev rule creates /dev/{name})
        dev_path = f"/dev/{device.name}" if device.usb_path else f"/dev/ttyUSB{i}"

        lines.extend([
            f"",
            f"connection: &{device.name.replace('-', '_')}",
            f"  accepter: telnet(rfc2217),tcp,{device.remote_port}",
            f"  connector: serialdev,{dev_path},{baud}n81,local",
            f"  options:",
            f"    kickolduser: true",
        ])

    return "\n".join(lines) + "\n"


def install_ser2net(ssh: SSHConnection, config: str) -> tuple[bool, str]:
    """Install ser2net and config on remote host."""
    # Check/install ser2net
    out, err, code = ssh.run("which ser2net || sudo apt-get install -y ser2net")
    if code != 0 and "permission denied" in err.lower():
        return False, "Need sudo password for ser2net install"

    # Write config
    # Escape single quotes in config
    safe_config = config.replace("'", "'\"'\"'")
    out, err, code = ssh.run(f"echo '{safe_config}' | sudo tee /etc/ser2net.yaml > /dev/null")
    if code != 0:
        return False, f"Failed to write config: {err}"

    # Restart service
    out, err, code = ssh.run("sudo systemctl restart ser2net && sudo systemctl enable ser2net")
    if code != 0:
        return False, f"Failed to restart ser2net: {err}"

    return True, "ser2net configured and restarted"


def get_ser2net_status(ssh: SSHConnection) -> dict:
    """Get ser2net status from remote."""
    out, err, code = ssh.run("systemctl is-active ser2net")
    active = out.strip() == "active"

    out, err, code = ssh.run("cat /etc/ser2net.yaml 2>/dev/null || echo ''")
    config = out if code == 0 else ""

    return {
        "active": active,
        "config": config,
    }
