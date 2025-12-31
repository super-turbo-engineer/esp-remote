"""SSH operations for esp-remote."""

import os
import signal
import subprocess
import time
from typing import Optional, Callable

import paramiko


class SSHConnection:
    """SSH connection wrapper."""

    def __init__(self, host: str):
        # Parse user@hostname
        if "@" in host:
            self.user, self.hostname = host.split("@", 1)
        else:
            self.user = os.environ.get("USER", "pi")
            self.hostname = host

        self.host = f"{self.user}@{self.hostname}"
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self):
        """Establish SSH connection."""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(self.hostname, username=self.user)

    def close(self):
        """Close connection."""
        if self._client:
            self._client.close()
            self._client = None

    def run(self, cmd: str) -> tuple[str, str, int]:
        """Run command and return stdout, stderr, exit code."""
        if not self._client:
            raise RuntimeError("Not connected")
        _, stdout, stderr = self._client.exec_command(cmd)
        return (
            stdout.read().decode(),
            stderr.read().decode(),
            stdout.channel.recv_exit_status(),
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()


def find_tunnel_pid(port: int) -> Optional[int]:
    """Find SSH tunnel process for given port."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"ssh.*-L {port}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return int(result.stdout.strip().split()[0])
    except Exception:
        pass
    return None


def is_port_open(port: int) -> bool:
    """Check if local port is listening."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            return True
    except Exception:
        return False


def create_tunnel(host: str, local_port: int, remote_port: int) -> bool:
    """Create SSH tunnel in background."""
    # Parse host
    if "@" in host:
        user, hostname = host.split("@", 1)
    else:
        user = os.environ.get("USER", "pi")
        hostname = host

    # Kill existing tunnel on this port
    pid = find_tunnel_pid(local_port)
    if pid:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)

    # Create tunnel
    cmd = [
        "ssh",
        "-f",
        "-N",
        "-L",
        f"{local_port}:127.0.0.1:{remote_port}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        f"{user}@{hostname}",
    ]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        return False

    time.sleep(1)
    return is_port_open(local_port)


def kill_tunnel(port: int) -> bool:
    """Kill SSH tunnel on given port."""
    pid = find_tunnel_pid(port)
    if pid:
        os.kill(pid, signal.SIGTERM)
        return True
    return False
