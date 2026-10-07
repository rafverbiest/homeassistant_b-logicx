"""Turn two wire bytes into a BLXEvent, and the other way around.

Layout of one datagram, first byte first:

  byte 0        address, 0–255
  byte 1 high   command code, 0–15 (COMMAND_CODES in const.py)
  byte 1 low    group, 0–15

Set on group 2, address 80 is the bytes 0x50 0x32, written "Set 2.80".
"""

from __future__ import annotations

from .const import COMMAND_CODES, COMMAND_NAMES
from .models import BLXEvent


def encode_datagram(command: str | int, group: int, address: int) -> bytes:
    """Build the two wire bytes from a command, group and address.

    A command name is matched without case ("set" and "Set" are the same) but must
    be one of the 16 names. A number is used directly as the command code.
    """
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
    """Split exactly two bytes into command, group and address.

    A high half that is not in COMMAND_CODES is named "UNK" plus the number,
    so the frame is still visible.
    """
    if len(data) != 2:
        raise ValueError("Datagram must be exactly 2 bytes")
    cmd_code = (data[1] & 0xF0) >> 4
    group = data[1] & 0x0F
    address = data[0]
    command = COMMAND_CODES.get(cmd_code, f"UNK{cmd_code}")
    return BLXEvent(command=command, group=group, address=address, raw=data)
