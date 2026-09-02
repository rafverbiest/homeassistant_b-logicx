"""Encode/decode 2-byte B-Logicx datagrams (shared by library, fake gateway, tests)."""

from __future__ import annotations

from .const import COMMAND_CODES, COMMAND_NAMES
from .models import BLXEvent


def encode_datagram(command: str | int, group: int, address: int) -> bytes:
    """Build a 2-byte datagram: byte0=address, byte1=(cmd<<4)|group."""
    if isinstance(command, str):
        cmd_name = command.title()
        if cmd_name not in COMMAND_NAMES:
            raise ValueError(f"Unknown command: {command}")
        code = COMMAND_NAMES[cmd_name]
    else:
        code = int(command)

    value = (code << 4) | (group & 0x0F) | ((address & 0xFF) << 8)
    return value.to_bytes(2, byteorder="big", signed=False)


def decode_datagram(data: bytes) -> BLXEvent:
    """Decode exactly 2 bytes into a BLXEvent."""
    if len(data) != 2:
        raise ValueError("Datagram must be exactly 2 bytes")
    cmd_code = (data[1] & 0xF0) >> 4
    group = data[1] & 0x0F
    address = data[0]
    command = COMMAND_CODES.get(cmd_code, f"UNK{cmd_code}")
    return BLXEvent(command=command, group=group, address=address, raw=data)
