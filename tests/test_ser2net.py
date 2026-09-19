from esp_remote.registry import Device
from esp_remote.ser2net import generate_config


def _device(name: str, remote_port: int) -> Device:
    return Device(
        name=name,
        chip_id="0x00000001",
        host="pi@raspberrypi",
        usb_path="1-1",
        remote_port=remote_port,
        local_port=remote_port,
    )


def test_every_serial_port_listens_on_loopback_only():
    config = generate_config([_device("esp-a", 4000), _device("esp-b", 4001)])

    accepters = [line.strip() for line in config.splitlines() if "accepter:" in line]

    assert accepters == [
        "accepter: telnet(rfc2217),tcp,127.0.0.1,4000",
        "accepter: telnet(rfc2217),tcp,127.0.0.1,4001",
    ]
