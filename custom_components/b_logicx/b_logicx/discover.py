"""Find an NWM or NWX on the local network.

BLConfig broadcasts four bytes, 00 00 00 F8, to UDP port 30718. That port
is the Lantronix discovery port, and the gateway's Ethernet side is a
Lantronix module. The module answers from its own address with a setup
record, 00 00 00 F9. An NWM or NWX record has a channel on TCP port
10001. The bytes at the end are the DHCP hostname, when the router gave
the module one. The sender address is the gateway. A second query,
00 00 00 F6, asks for the firmware record: the MAC and the version.
This module sends both reads, and it can build the replies the bus
repeater sends while it is listening.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
import struct
from pathlib import Path
from typing import NamedTuple

_LOGGER = logging.getLogger(__name__)

# UDP port 30718, 0x77FE. The query asks for the setup record.
DISCOVER_PORT = 30718
DISCOVER_QUERY = b"\x00\x00\x00\xf8"
_FIRMWARE_QUERY = b"\x00\x00\x00\xf6"
DISCOVER_WAIT_S = 1.0
_FIRMWARE_WAIT_S = 0.5

# 30-byte F7 from the captured NWM. BLConfig reads the parentheses from
# bytes 6 and 7, and the MAC from the last six bytes. The repeater answers
# with the MAC below. The parentheses follow the manifest version.
_FIRMWARE_REPLY = bytes.fromhex(
    "000000f70020a006465957124b16000062a7adb7ff00000000204af00921"
)
# A5-51-57-10-00-00. The hex digits stand in for letters: A stays A, 5 is S,
# 1 is I, 7 is T, and 0 is O. Read in order that is ASSISTIO. The last two
# pairs are 00 because a MAC is six bytes.
_REPEATER_MAC = bytes.fromhex("a55157100000")

_GATEWAY_MARK = b"b-logicx"
_SETUP_REPLY = 0xF9

# 120-byte setup record from a captured NWM, with the second channel left
# empty. The repeater reports only the TCP port it opened. That port is
# little-endian at byte 24 of the whole datagram.
_RECORD_PREFIX = bytes.fromhex("000005000000002d0000000000000000")
_CHANNEL_HEAD = bytes.fromhex("4c020200")
_CHANNEL_AFTER_PORT = bytes.fromhex("000000000000c00000000000f700") + bytes(28)
# Both captured modules advertise this channel. The hostname is not part of it.
_MODULE_CHANNEL = _CHANNEL_HEAD + (10001).to_bytes(2, "little")
_NAME_LEN = 8
_FIRMWARE_MARK = b"\x00\x00\x00\xf7"


def build_setup_record(port: int) -> bytes:
    """F9 setup record naming one TCP port and the hostname b-logicx."""
    channel = _CHANNEL_HEAD + port.to_bytes(2, "little") + _CHANNEL_AFTER_PORT
    return b"\x00\x00\x00\xf9" + _RECORD_PREFIX + channel + bytes(48) + _GATEWAY_MARK


def manifest_version() -> str:
    """Version from manifest.json, the same string Home Assistant shows."""
    path = Path(__file__).resolve().parents[1] / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "0.0"
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else "0.0"


def _first_digit(component: str) -> int:
    """First decimal digit in a version component, or 0 when there is none."""
    for char in component:
        if char.isdigit():
            return int(char)
    return 0


def version_octets(version: str) -> bytes:
    """F7 bytes for the first digit of each of the first two version components.

    The parentheses hold one digit on each side, so 0.9.9.5 is shown as (0.9).
    """
    parts = version.split(".")
    major = _first_digit(parts[0] if parts else "")
    minor = _first_digit(parts[1] if len(parts) > 1 else "")
    return bytes((minor << 4, major))


def firmware_reply(mac: bytes) -> bytes | None:
    """Captured F7 with the manifest version and the MAC it is given.

    Byte 7 is the major and the high nibble of byte 6 is the minor, the
    same places that read (6.A) and (6.7) on the captured modules.
    """
    if len(mac) != 6:
        return None
    head = bytearray(_FIRMWARE_REPLY[:24])
    head[6:8] = version_octets(manifest_version())
    return bytes(head) + mac


def reply_to_discover(query: bytes, port: int) -> bytes | None:
    """Setup record for F8. For F6, the ASSISTIO MAC and the manifest version."""
    if query == DISCOVER_QUERY:
        return build_setup_record(port)
    if query != _FIRMWARE_QUERY:
        return None
    return firmware_reply(_REPEATER_MAC)


class DiscoveredGateway(NamedTuple):
    """One module found on the LAN. A missing detail is left off the row."""

    ip: str
    mac: str | None = None
    hostname: str | None = None
    version: str | None = None

    @property
    def label(self) -> str:
        """IP, MAC, hostname, and firmware version, skipping what we did not learn."""
        parts = [self.ip]
        if self.mac:
            parts.append(self.mac)
        if self.hostname:
            parts.append(self.hostname)
        if self.version:
            parts.append(self.version)
        return " · ".join(parts)


def is_gateway_reply(payload: bytes) -> bool:
    """True when this datagram is an NWM or NWX setup record.

    The trailing hostname is optional. The record has to advertise the
    TCP channel on port 10001.
    """
    return (
        len(payload) >= 4
        and payload[:3] == b"\x00\x00\x00"
        and payload[3] == _SETUP_REPLY
        and _MODULE_CHANNEL in payload
    )


def setup_hostname(payload: bytes) -> str | None:
    """DHCP hostname in the last eight bytes, when those bytes are printable."""
    if len(payload) < _NAME_LEN:
        return None
    raw = payload[-_NAME_LEN:].split(b"\x00", 1)[0]
    if not raw or any(byte < 0x20 or byte > 0x7E for byte in raw):
        return None
    return raw.decode("ascii")


def firmware_mac(payload: bytes) -> str | None:
    """MAC from an F7, dashed and uppercase, as BLConfig prints it."""
    if len(payload) < 30 or payload[:4] != _FIRMWARE_MARK:
        return None
    return "-".join(f"{byte:02X}" for byte in payload[-6:])


def firmware_version(payload: bytes) -> str | None:
    """Firmware version from an F7. Byte 7 is the major, the high nibble of byte 6 the minor."""
    if len(payload) < 8 or payload[:4] != _FIRMWARE_MARK:
        return None
    minor = payload[6] >> 4
    major = payload[7]
    return f"{major:X}.{minor:X}"


def gateway_step_id(ip: str) -> str:
    """Menu step id for one discovered address. Dots are not valid in a step id."""
    return "gw_" + ip.replace(".", "_")


def ip_from_gateway_step(step_id: str) -> str | None:
    """Address encoded by gateway_step_id, or None when the id is not one."""
    if not step_id.startswith("gw_"):
        return None
    text = step_id.removeprefix("gw_").replace("_", ".")
    try:
        return str(ipaddress.IPv4Address(text))
    except ValueError:
        return None


def local_ipv4_addresses() -> set[str]:
    """IPv4 addresses of this host. A discovery reply from one of them is our repeater."""
    found = {"127.0.0.1"}
    if not hasattr(socket, "if_nameindex"):
        return found
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _index, name in socket.if_nameindex():
            encoded = name.encode()[:15]
            try:
                # SIOCGIFADDR. The IPv4 address starts at byte 20.
                packed = fcntl_ioctl(
                    sock, 0x8915, struct.pack("16s16s", encoded, b"\x00" * 16)
                )
                ip = socket.inet_ntoa(packed[20:24])
            except OSError:
                continue
            if ip != "0.0.0.0":
                found.add(ip)
    finally:
        sock.close()
    return found


def broadcast_targets() -> list[str]:
    """Limited broadcast, plus each interface's directed broadcast.

    255.255.255.255 is what BLConfig sends. A directed broadcast covers
    a host where the limited broadcast stays on the wrong interface.
    """
    targets = ["255.255.255.255"]
    if not hasattr(socket, "if_nameindex"):
        return targets
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _index, name in socket.if_nameindex():
            encoded = name.encode()[:15]
            try:
                # SIOCGIFFLAGS. Skip loopback. Keep interfaces that broadcast.
                flags = struct.unpack(
                    "16xH",
                    fcntl_ioctl(sock, 0x8913, struct.pack("16sH", encoded, 0)),
                )[0]
                if flags & 0x8 or not flags & 0x2:
                    continue
                # SIOCGIFBRDADDR. The IPv4 address starts at byte 20.
                packed = fcntl_ioctl(
                    sock, 0x8919, struct.pack("16s16s", encoded, b"\x00" * 16)
                )
                ip = socket.inet_ntoa(packed[20:24])
            except OSError:
                continue
            if ip == "0.0.0.0" or ip in targets:
                continue
            targets.append(ip)
    finally:
        sock.close()
    return targets


def fcntl_ioctl(sock: socket.socket, request: int, buf: bytes) -> bytes:
    """ioctl wrapper so the address scan can be imported without fcntl."""
    import fcntl

    return fcntl.ioctl(sock, request, buf)


async def _recv_until(loop, sock: socket.socket, deadline: float):
    """Next datagram before the deadline, or None when time runs out."""
    remaining = deadline - loop.time()
    if remaining <= 0:
        return None
    try:
        return await asyncio.wait_for(loop.sock_recvfrom(sock, 512), remaining)
    except TimeoutError:
        return None


async def discover_gateways(timeout: float = DISCOVER_WAIT_S) -> list[DiscoveredGateway]:
    """Broadcast the setup query and return each module that answers.

    After the setup records are in, each module is asked for its firmware
    record. The row still lists a module when that second answer does not arrive.
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setblocking(False)
    try:
        sock.bind(("0.0.0.0", 0))
    except OSError:
        _LOGGER.debug("Discovery socket could not bind", exc_info=True)
        sock.close()
        return []

    sent = False
    try:
        for target in broadcast_targets():
            try:
                await loop.sock_sendto(sock, DISCOVER_QUERY, (target, DISCOVER_PORT))
                sent = True
            except OSError:
                _LOGGER.debug("Discovery broadcast to %s failed", target, exc_info=True)
        if not sent:
            return []

        found: dict[str, DiscoveredGateway] = {}
        own = local_ipv4_addresses()
        deadline = loop.time() + timeout
        while True:
            got = await _recv_until(loop, sock, deadline)
            if got is None:
                break
            data, addr = got
            ip, port = addr[0], addr[1]
            if port != DISCOVER_PORT or ip in own or not is_gateway_reply(data):
                continue
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                continue
            if ip not in found:
                found[ip] = DiscoveredGateway(ip, hostname=setup_hostname(data))
        if not found:
            return []

        for ip in found:
            try:
                await loop.sock_sendto(sock, _FIRMWARE_QUERY, (ip, DISCOVER_PORT))
            except OSError:
                _LOGGER.debug("Firmware query to %s failed", ip, exc_info=True)
        deadline = loop.time() + _FIRMWARE_WAIT_S
        while True:
            got = await _recv_until(loop, sock, deadline)
            if got is None:
                break
            data, addr = got
            ip, port = addr[0], addr[1]
            if port != DISCOVER_PORT or ip not in found or data[:4] != _FIRMWARE_MARK:
                continue
            found[ip] = found[ip]._replace(
                mac=firmware_mac(data),
                version=firmware_version(data),
            )
            if all(item.mac for item in found.values()):
                break
        ordered = [found[ip] for ip in sorted(found, key=ipaddress.IPv4Address)]
        _LOGGER.debug("Discovered gateways: %s", [item.label for item in ordered])
        return ordered
    finally:
        sock.close()
