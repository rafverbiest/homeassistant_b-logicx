"""B-Logicx RTC (bus clock) Program sequence — pure helpers, no HA.

Legacy script packs time fields as 4 hex characters, then byte-swaps
(``ABCD`` → wire ``CD AB``), identical to normal datagrams. Payload frames
still decode as command/group/address; the command nibble is an artifact of
packing, not an intentional bus action. The RTC accepts them as register
data because they follow a Program command.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .protocol import decode_datagram, encode_datagram

# (command_name, group, address)
RtcFrame = tuple[str, int, int]


def legacy_hex4_to_raw(hex4: str) -> bytes:
    """Convert a 4-char legacy hex string to 2 wire bytes (byte-swapped)."""
    if len(hex4) != 4:
        raise ValueError(f"expected 4 hex chars, got {hex4!r}")
    return bytes.fromhex(hex4[2:4] + hex4[0:2])


def legacy_hex4_to_frame(hex4: str) -> RtcFrame:
    """Decode a legacy hex4 string into (command, group, address)."""
    event = decode_datagram(legacy_hex4_to_raw(hex4))
    return (event.command, event.group, event.address)


def program_hex4(group: int, address: int) -> str:
    """Legacy Program target string, e.g. group=1 address=1 → ``f101``."""
    return f"f{(group & 0x0F):x}{(address & 0xFF):02x}"


def build_rtc_sync_hex4(
    when: datetime,
    group: int = 1,
    address: int = 1,
) -> list[str]:
    """Nine legacy hex4 strings for a full RTC time write."""
    prog = program_hex4(group, address)
    minute = when.minute
    second = when.second
    weekday = when.weekday() + 1  # Mon=1 … Sun=7
    hour = when.hour
    month = when.month
    day = when.day
    return [
        prog,
        f"{minute:02d}{second:02d}",
        "0003",
        prog,
        f"{weekday:02d}{hour:02d}",
        "0004",
        prog,
        f"{month:02d}{day:02d}",
        "0005",
    ]


def build_rtc_sync_frames(
    when: datetime,
    group: int = 1,
    address: int = 1,
) -> list[RtcFrame]:
    """Nine (command, group, address) frames for ``BLXConnection.send``."""
    return [legacy_hex4_to_frame(h) for h in build_rtc_sync_hex4(when, group, address)]


def build_rtc_sync_raw(
    when: datetime,
    group: int = 1,
    address: int = 1,
) -> list[bytes]:
    """Nine raw 2-byte datagrams (byte-identical to the legacy socket script)."""
    return [legacy_hex4_to_raw(h) for h in build_rtc_sync_hex4(when, group, address)]


def frames_to_raw(frames: Iterable[RtcFrame]) -> list[bytes]:
    """Encode (command, group, address) triples to wire bytes."""
    return [encode_datagram(cmd, g, a) for cmd, g, a in frames]


def describe_rtc_frame(index: int, frame: RtcFrame, when: datetime | None = None) -> str:
    """Human annotation for tests / DEBUG (index 0..8)."""
    cmd, g, a = frame
    base = f"{cmd} {g}.{a}"
    notes = {
        0: "Program (RTC)",
        1: "RTC data reg3 (minute/second)",
        2: "RTC select register 3",
        3: "Program (RTC)",
        4: "RTC data reg4 (weekday/hour)",
        5: "RTC select register 4",
        6: "Program (RTC)",
        7: "RTC data reg5 (month/day)",
        8: "RTC select register 5",
    }
    note = notes.get(index, "RTC")
    if when is not None and index == 1:
        note = f"RTC data: minute={when.minute} second={when.second}"
    elif when is not None and index == 4:
        note = f"RTC data: weekday={when.weekday() + 1} hour={when.hour}"
    elif when is not None and index == 7:
        note = f"RTC data: month={when.month} day={when.day}"
    return f"{base}  # {note}"


def next_phased_sync(
    now: datetime,
    interval_hours: float = 12,
    sync_minute: int = 17,
) -> datetime:
    """Next wall-clock sync at ``:sync_minute``, on an interval-hour grid from midnight.

    Examples with ``sync_minute=17``, ``interval_hours=12``: 00:17 and 12:17.
    Never intentionally lands on ``:00`` unless ``sync_minute`` is 0.
    """
    interval_h = max(1, int(round(float(interval_hours))))
    minute = max(0, min(59, int(sync_minute)))
    # Search a few days of candidates
    from datetime import timedelta

    day0 = now.replace(hour=0, minute=minute, second=0, microsecond=0)
    for day_offset in range(0, 5):
        day_base = day0 + timedelta(days=day_offset)
        for hour in range(0, 24, interval_h):
            candidate = day_base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now:
                return candidate
    return now + timedelta(hours=interval_h)
