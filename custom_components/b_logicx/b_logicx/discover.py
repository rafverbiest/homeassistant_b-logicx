"""Find an NWM or NWX on the local network.

BLConfig broadcasts four bytes, 00 00 00 F8, to UDP port 30718. That port
is the Lantronix discovery port, and the gateway's Ethernet side is a
Lantronix module. The module answers from its own address with a setup
record, 00 00 00 F9. An NWM or NWX record contains the text b-logicx.
The sender address is the gateway. This module only sends that read.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import struct

_LOGGER = logging.getLogger(__name__)

# UDP port 30718, 0x77FE. The query asks for the setup record.
DISCOVER_PORT = 30718
DISCOVER_QUERY = b"\x00\x00\x00\xf8"
DISCOVER_WAIT_S = 1.0

_GATEWAY_MARK = b"b-logicx"
_SETUP_REPLY = 0xF9


def is_gateway_reply(payload: bytes) -> bool:
    """True when this datagram is an NWM or NWX setup record."""
    return (
        len(payload) >= 4
        and payload[:3] == b"\x00\x00\x00"
        and payload[3] == _SETUP_REPLY
        and _GATEWAY_MARK in payload.lower()
    )


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


async def discover_gateways(timeout: float = DISCOVER_WAIT_S) -> list[str]:
    """Broadcast the setup query and return the gateway addresses that answer."""
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

        found: set[str] = set()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, addr = await asyncio.wait_for(
                    loop.sock_recvfrom(sock, 512), remaining
                )
            except TimeoutError:
                break
            ip, port = addr[0], addr[1]
            if port != DISCOVER_PORT or not is_gateway_reply(data):
                continue
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                continue
            found.add(ip)
        ordered = sorted(found, key=ipaddress.IPv4Address)
        _LOGGER.debug("Discovered gateways: %s", ordered)
        return ordered
    finally:
        sock.close()
