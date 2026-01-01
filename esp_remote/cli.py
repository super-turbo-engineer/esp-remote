"""CLI entry point for esp-remote."""

import sys

import click
from rich.console import Console
from rich.table import Table

from . import git_ops
from .config import ensure_dirs, REGISTRY_DIR
from .esptool_utils import scan_devices_remote, verify_chip_id
from .registry import Device, Registry
from .ser2net import generate_config, install_ser2net, get_ser2net_status
from .ssh import SSHConnection, create_tunnel, kill_tunnel, is_port_open
from .udev import generate_rules, install_rules, save_rules, get_usb_path

console = Console()


@click.group()
@click.version_option()
def main():
    """Remote ESP development with device registry.

    Manage ESP devices connected to remote Linux hosts (Raspberry Pi, etc.)
    with persistent naming, multi-device support, and git-tracked registry.

    Quick start:

        esp-remote init-registry             # Initialize registry
        esp-remote scan pi@raspberrypi       # Find devices
        esp-remote register myesp            # Register a device
        esp-remote connect myesp             # Connect via SSH tunnel
        pio run -t upload                    # Upload firmware
    """
    ensure_dirs()


# --- Registry Management ---


@main.command("init-registry")
@click.argument("git_url", required=False)
def init_registry(git_url):
    """Initialize device registry.

    Optionally clone from a git URL for syncing across machines.
    """
    if git_ops.is_git_repo():
        console.print("[yellow]Registry already initialized[/yellow]")
        console.print(f"  Location: {REGISTRY_DIR}")
        return

    try:
        if git_url:
            console.print(f"[cyan]Cloning registry from {git_url}...[/cyan]")
        else:
            console.print("[cyan]Initializing new registry...[/cyan]")

        git_ops.init_registry(git_url)
        console.print(f"[green]Registry initialized at {REGISTRY_DIR}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to initialize: {e}[/red]")
        sys.exit(1)


@main.command()
def sync():
    """Sync registry with git remote."""
    status = git_ops.status()

    if not status.get("initialized"):
        console.print("[red]Registry not initialized. Run: esp-remote init-registry[/red]")
        sys.exit(1)

    console.print("[cyan]Syncing registry...[/cyan]")
    success, message = git_ops.sync()

    if success:
        console.print(f"[green]{message}[/green]")
    else:
        console.print(f"[red]{message}[/red]")
        sys.exit(1)


# --- Device Scanning & Registration ---


@main.command()
@click.argument("host")
def scan(host):
    """Scan remote host for ESP devices.

    Shows chip-id for each device found.
    """
    console.print(f"[cyan]Scanning {host} for ESP devices...[/cyan]")

    try:
        with SSHConnection(host) as ssh:
            results = scan_devices_remote(ssh)

            if not results:
                console.print("[yellow]No serial devices found[/yellow]")
                return

            table = Table(title="ESP Devices Found")
            table.add_column("Device", style="cyan")
            table.add_column("Chip Type")
            table.add_column("ID (chip_id or MAC)", style="green")
            table.add_column("USB Path")

            for device, chip_info in results:
                usb_path = get_usb_path(ssh, device)

                if chip_info:
                    # Use chip_id if available, otherwise MAC
                    device_id = chip_info.chip_id or chip_info.mac or ""
                    table.add_row(
                        device,
                        chip_info.chip_type,
                        device_id,
                        usb_path,
                    )
                else:
                    table.add_row(device, "[dim]Unknown[/dim]", "", usb_path)

            console.print(table)
            console.print()
            console.print("To register a device:")
            console.print(
                f"  [cyan]esp-remote register <name> --chip-id <id> --host {host}[/cyan]"
            )

    except Exception as e:
        console.print(f"[red]Failed to scan: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("name")
@click.option("--chip-id", required=True, help="Chip ID from scan")
@click.option("--host", required=True, help="Host (user@hostname)")
@click.option("--usb-path", default="", help="USB path for udev rule")
@click.option("--description", "-d", default="", help="Device description")
def register(name, chip_id, host, usb_path, description):
    """Register a device in the registry."""
    registry = Registry()

    # Check for existing - preserve port if updating
    existing = registry.get_device(name)
    if existing:
        console.print(f"[yellow]Device '{name}' already exists. Updating...[/yellow]")
        port = existing.remote_port  # Keep existing port
    else:
        port = registry.next_port(host)

    device = Device(
        name=name,
        chip_id=chip_id,
        host=host,
        usb_path=usb_path,
        remote_port=port,
        local_port=port,
        description=description,
    )

    registry.add_device(device)
    console.print(f"[green]Registered '{name}'[/green]")
    console.print(f"  Chip ID: {chip_id}")
    console.print(f"  Host: {host}")
    console.print(f"  Port: {port}")

    if usb_path:
        console.print(f"  USB Path: {usb_path}")
        console.print()
        console.print("To install udev rules: [cyan]esp-remote udev-install[/cyan]")


@main.command()
@click.argument("name")
def unregister(name):
    """Remove a device from the registry."""
    registry = Registry()

    if registry.remove_device(name):
        console.print(f"[green]Removed '{name}'[/green]")
    else:
        console.print(f"[red]Device '{name}' not found[/red]")
        sys.exit(1)


# --- Connection Management ---


@main.command()
@click.argument("device", required=False)
def connect(device):
    """Connect to a device via SSH tunnel.

    If no device specified, connects to all devices on all hosts.
    """
    registry = Registry()

    if device:
        dev = registry.get_device(device)
        if not dev:
            console.print(f"[red]Device '{device}' not found[/red]")
            console.print("Run: [cyan]esp-remote status[/cyan] to see registered devices")
            sys.exit(1)
        devices = [dev]
    else:
        devices = registry.list_devices()
        if not devices:
            console.print("[yellow]No devices registered[/yellow]")
            console.print("Run: [cyan]esp-remote scan <host>[/cyan] to find devices")
            return

    for dev in devices:
        if is_port_open(dev.local_port):
            console.print(f"[yellow]{dev.name}[/yellow]: Already connected (port {dev.local_port})")
            continue

        console.print(f"[cyan]{dev.name}[/cyan]: Connecting to {dev.host}...")

        if create_tunnel(dev.host, dev.local_port, dev.remote_port):
            console.print(f"[green]{dev.name}[/green]: Connected on port {dev.local_port}")
            console.print(f"  Upload: rfc2217://localhost:{dev.local_port}")
        else:
            console.print(f"[red]{dev.name}[/red]: Failed to connect")


@main.command()
@click.argument("device", required=False)
def disconnect(device):
    """Disconnect from device(s)."""
    registry = Registry()

    if device:
        dev = registry.get_device(device)
        if not dev:
            console.print(f"[red]Device '{device}' not found[/red]")
            sys.exit(1)
        devices = [dev]
    else:
        devices = registry.list_devices()

    for dev in devices:
        if kill_tunnel(dev.local_port):
            console.print(f"[green]{dev.name}[/green]: Disconnected")
        else:
            console.print(f"[dim]{dev.name}[/dim]: Not connected")


@main.command()
def status():
    """Show all devices and connection status."""
    registry = Registry()
    devices = registry.list_devices()

    if not devices:
        console.print("[yellow]No devices registered[/yellow]")
        console.print("Run: [cyan]esp-remote scan <host>[/cyan] to find devices")
        return

    table = Table(title="Device Status")
    table.add_column("Device", style="cyan")
    table.add_column("Chip ID")
    table.add_column("Host")
    table.add_column("Port")
    table.add_column("Status")
    table.add_column("Upload Port")

    for dev in devices:
        connected = is_port_open(dev.local_port)
        status_str = "[green]Connected[/green]" if connected else "[dim]Disconnected[/dim]"
        upload = f"rfc2217://localhost:{dev.local_port}" if connected else ""

        table.add_row(
            dev.name,
            dev.chip_id,
            dev.host,
            str(dev.local_port),
            status_str,
            upload,
        )

    console.print(table)

    # Git status
    git_status = git_ops.status()
    if git_status.get("initialized"):
        if git_status.get("dirty"):
            console.print("\n[yellow]Registry has uncommitted changes[/yellow]")
            console.print("Run: [cyan]esp-remote sync[/cyan] to commit and push")


# --- Device Operations ---


@main.command()
@click.argument("device")
def verify(device):
    """Verify device chip-id matches registry."""
    registry = Registry()

    dev = registry.get_device(device)
    if not dev:
        console.print(f"[red]Device '{device}' not found[/red]")
        sys.exit(1)

    if not is_port_open(dev.local_port):
        console.print(f"[red]Not connected to {device}. Run: esp-remote connect {device}[/red]")
        sys.exit(1)

    console.print(f"[cyan]Verifying {device}...[/cyan]")

    try:
        with SSHConnection(dev.host) as ssh:
            # Use the symlink if udev is set up
            dev_path = f"/dev/{dev.name}" if dev.usb_path else "/dev/ttyUSB0"
            success, message = verify_chip_id(ssh, dev_path, dev.chip_id)

            if success:
                console.print(f"[green]{message}[/green]")
            else:
                console.print(f"[red]{message}[/red]")
                sys.exit(1)
    except Exception as e:
        console.print(f"[red]Verification failed: {e}[/red]")
        sys.exit(1)


def _detect_baud_rate(port: int) -> int:
    """Try common baud rates and return one that gives ASCII output."""
    import serial

    common_rates = [115200, 9600, 74880, 57600, 38400, 19200, 4800]

    for baud in common_rates:
        try:
            ser = serial.serial_for_url(
                f"rfc2217://localhost:{port}", baudrate=baud, timeout=0.5
            )
            # Read some data
            data = ser.read(100)
            ser.close()

            if len(data) < 5:
                continue

            # Check if mostly printable ASCII
            printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
            ratio = printable / len(data)

            if ratio > 0.7:  # 70% printable = likely correct
                return baud
        except Exception:
            continue

    return 115200  # Default fallback


@main.command()
@click.argument("device")
@click.option("-b", "--baud", default=None, type=int, help="Baud rate (auto-detect if not specified)")
@click.option("--raw", is_flag=True, help="Raw output mode (no interactive input)")
def monitor(device, baud, raw):
    """Open serial monitor for a device."""
    import select

    registry = Registry()

    dev = registry.get_device(device)
    if not dev:
        console.print(f"[red]Device '{device}' not found[/red]")
        sys.exit(1)

    if not is_port_open(dev.local_port):
        console.print(f"[red]Not connected. Run: esp-remote connect {device}[/red]")
        sys.exit(1)

    # Auto-detect baud rate if not specified
    if baud is None:
        console.print(f"[cyan]Auto-detecting baud rate...[/cyan]")
        baud = _detect_baud_rate(dev.local_port)
        console.print(f"[green]Detected: {baud}[/green]")

    console.print(f"[cyan]Connecting to {device} @ {baud}...[/cyan]")
    console.print("[dim]Press Ctrl+C to exit[/dim]\n")

    try:
        import serial

        ser = serial.serial_for_url(
            f"rfc2217://localhost:{dev.local_port}", baudrate=baud
        )
    except ImportError:
        console.print("[red]pyserial not installed[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to connect: {e}[/red]")
        sys.exit(1)

    is_tty = sys.stdin.isatty() and not raw
    old_settings = None

    if is_tty:
        import termios
        import tty

        old_settings = termios.tcgetattr(sys.stdin)

    try:
        if is_tty:
            import tty

            tty.setraw(sys.stdin.fileno())

        ser.timeout = 0.1

        while True:
            data = ser.read(ser.in_waiting or 1)
            if data:
                if is_tty:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                else:
                    sys.stdout.write(data.decode("utf-8", errors="replace"))
                    sys.stdout.flush()

            if is_tty:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if readable:
                    char = sys.stdin.read(1)
                    if char == "\x03":
                        raise KeyboardInterrupt
                    ser.write(char.encode())

    except KeyboardInterrupt:
        pass
    finally:
        if old_settings:
            import termios

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        ser.close()
        console.print("\n[yellow]Disconnected[/yellow]")


# --- Setup & Configuration ---


@main.command()
@click.argument("host")
def setup(host):
    """Set up ser2net on remote host.

    Installs ser2net and configures it for all registered devices on this host.
    """
    registry = Registry()
    devices = registry.get_devices_by_host(host)

    # Also check with parsed host
    if "@" in host:
        user, hostname = host.split("@", 1)
        full_host = f"{user}@{hostname}"
    else:
        import os
        full_host = f"{os.environ.get('USER', 'pi')}@{host}"
        devices = devices or registry.get_devices_by_host(full_host)

    if not devices:
        console.print(f"[yellow]No devices registered for {host}[/yellow]")
        console.print("Run: [cyan]esp-remote scan {host}[/cyan] first")
        return

    console.print(f"[cyan]Setting up ser2net on {host}...[/cyan]")
    console.print(f"  Devices: {', '.join(d.name for d in devices)}")

    config = generate_config(devices)

    try:
        with SSHConnection(host) as ssh:
            success, message = install_ser2net(ssh, config)

            if success:
                console.print(f"[green]{message}[/green]")

                # Show connection info
                console.print()
                for dev in devices:
                    console.print(f"  {dev.name}: port {dev.remote_port}")
            else:
                console.print(f"[red]{message}[/red]")
                sys.exit(1)
    except Exception as e:
        console.print(f"[red]Setup failed: {e}[/red]")
        sys.exit(1)


@main.command("udev-install")
@click.argument("host")
def udev_install(host):
    """Install udev rules on remote host.

    Creates persistent /dev/esp-<name> symlinks based on USB paths.
    """
    registry = Registry()

    # Get devices for host
    if "@" in host:
        user, hostname = host.split("@", 1)
        full_host = f"{user}@{hostname}"
    else:
        import os
        full_host = f"{os.environ.get('USER', 'pi')}@{host}"

    devices = registry.get_devices_by_host(host) or registry.get_devices_by_host(full_host)

    if not devices:
        console.print(f"[yellow]No devices registered for {host}[/yellow]")
        return

    # Filter to devices with USB paths
    devices_with_path = [d for d in devices if d.usb_path]

    if not devices_with_path:
        console.print("[yellow]No devices have USB paths configured[/yellow]")
        console.print("Re-register with --usb-path or run scan to detect")
        return

    rules = generate_rules(devices_with_path)
    save_rules(devices_with_path)  # Save to registry

    console.print(f"[cyan]Installing udev rules on {host}...[/cyan]")

    try:
        with SSHConnection(host) as ssh:
            success, message = install_rules(ssh, rules)

            if success:
                console.print(f"[green]{message}[/green]")
                console.print()
                for dev in devices_with_path:
                    console.print(f"  /dev/{dev.name} -> USB path {dev.usb_path}")
            else:
                console.print(f"[red]{message}[/red]")
                sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to install rules: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("host", required=False)
def devices(host):
    """List serial devices on remote host."""
    registry = Registry()

    # Use first registered host if none specified
    if not host:
        all_devices = registry.list_devices()
        if all_devices:
            host = all_devices[0].host
        else:
            console.print("[red]No host specified and no devices registered[/red]")
            sys.exit(1)

    console.print(f"[cyan]Scanning {host}...[/cyan]")

    try:
        with SSHConnection(host) as ssh:
            out, _, code = ssh.run(
                "ls /dev/ttyUSB* /dev/ttyACM* /dev/ttyAMA* 2>/dev/null"
            )
            devices = [d.strip() for d in out.split() if d.strip()]

            if not devices:
                console.print("[yellow]No serial devices found[/yellow]")
                return

            table = Table(title="Serial Devices")
            table.add_column("Device", style="cyan")
            table.add_column("Info")

            for dev in devices:
                out, _, _ = ssh.run(
                    f"udevadm info -q property -n {dev} 2>/dev/null | "
                    "grep -E 'ID_MODEL=|ID_VENDOR=' | head -2"
                )
                info = (
                    out.strip()
                    .replace("\n", ", ")
                    .replace("ID_MODEL=", "")
                    .replace("ID_VENDOR=", "")
                )
                table.add_row(dev, info or "Unknown")

            console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list devices: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
