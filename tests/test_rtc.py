"""RTC protocol packing and schedule helpers (no Home Assistant)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from b_logicx import BLXConnection
from b_logicx.protocol import decode_datagram, encode_datagram
from b_logicx.rtc import (
    build_rtc_sync_frames,
    build_rtc_sync_hex4,
    build_rtc_sync_raw,
    describe_rtc_frame,
    legacy_hex4_to_raw,
    next_phased_sync,
    program_hex4,
)


def test_program_hex4():
    assert program_hex4(1, 1) == "f101"
    assert program_hex4(1, 15) == "f10f"


def test_legacy_pack_matches_known_table():
    """Frozen time from the design doc: 2026-07-22 14:35:42 Wednesday."""
    when = datetime(2026, 7, 22, 14, 35, 42)
    hex4 = build_rtc_sync_hex4(when, group=1, address=1)
    assert hex4 == [
        "f101",
        "3542",
        "0003",
        "f101",
        "0314",  # Wed=3, hour=14
        "0004",
        "f101",
        "0722",
        "0005",
    ]
    raw = build_rtc_sync_raw(when, 1, 1)
    assert raw[0] == bytes.fromhex("01f1")
    assert raw[1] == bytes.fromhex("4235")
    assert raw[2] == bytes.fromhex("0300")
    assert raw[4] == bytes.fromhex("1403")
    assert raw[7] == bytes.fromhex("2207")

    frames = build_rtc_sync_frames(when, 1, 1)
    assert frames[0] == ("Program", 1, 1)
    assert frames[1] == ("Set", 5, 66)
    assert frames[2] == ("Null", 0, 3)
    assert frames[4] == ("Null", 3, 20)
    assert frames[7] == ("Null", 7, 34)
    assert frames[8] == ("Null", 0, 5)

    # encode path is byte-identical to legacy raw
    for (cmd, g, a), r in zip(frames, raw, strict=True):
        assert encode_datagram(cmd, g, a) == r


def test_legacy_pack_reset_shaped_data_frame():
    """min=16 sec=19 → Reset 6.25 (command nibble is packing artifact)."""
    when = datetime(2026, 1, 5, 20, 16, 19)  # Monday=1
    frames = build_rtc_sync_frames(when, 1, 1)
    assert frames[1] == ("Reset", 6, 25)
    assert legacy_hex4_to_raw("1619") == encode_datagram("Reset", 6, 25)


def test_describe_rtc_frame():
    when = datetime(2026, 7, 22, 14, 35, 42)
    frames = build_rtc_sync_frames(when, 1, 1)
    assert "Program" in describe_rtc_frame(0, frames[0], when)
    assert "minute=35" in describe_rtc_frame(1, frames[1], when)


def test_next_phased_sync_not_on_the_hour():
    now = datetime(2026, 7, 22, 14, 0, 0)
    nxt = next_phased_sync(now, interval_hours=12, sync_minute=17)
    assert nxt.minute == 17
    assert nxt.second == 0
    # 00:17 and 12:17 grid; after 14:00 next is next day 00:17 or same day...
    # hours 0,12 only → after 14:00 → next day 00:17
    assert nxt == datetime(2026, 7, 23, 0, 17, 0)

    now2 = datetime(2026, 7, 22, 11, 0, 0)
    nxt2 = next_phased_sync(now2, interval_hours=12, sync_minute=17)
    assert nxt2 == datetime(2026, 7, 22, 12, 17, 0)


def test_next_phased_sync_after_phase_minute_same_slot():
    now = datetime(2026, 7, 22, 12, 17, 1)
    nxt = next_phased_sync(now, interval_hours=12, sync_minute=17)
    assert nxt == datetime(2026, 7, 23, 0, 17, 0)


@pytest.mark.asyncio
async def test_rtc_sync_send_over_fake_gateway(fake_gateway):
    """Nine frames appear on the wire in order."""
    gw = fake_gateway
    when = datetime(2026, 7, 22, 14, 35, 42)
    frames = build_rtc_sync_frames(when, 1, 1)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()
    for cmd, g, a in frames:
        await conn.send(cmd, g, a)
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)

    assert len(gw.rx_log) == 9
    for i, (cmd, g, a) in enumerate(frames):
        assert gw.rx_log[i].command == cmd
        assert gw.rx_log[i].group == g
        assert gw.rx_log[i].address == a

    # Bus log human lines exist
    assert any("[SENT] Program 1.1" in line for line in gw.bus_log)
    assert any("Set 5.66" in line for line in gw.bus_log)

    await conn.close()


def test_yaml_rtc_entry():
    from address_config import parse_addresses_yaml

    content = """
addresses:
  - type: rtc
    name: Bus clock
    group: 1
    address: 1
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert len(entries) == 1
    e = entries[0]
    assert e["type"] == "rtc"
    assert e["group"] == 1 and e["address"] == 1
    assert e["sync_on_startup"] is True
    assert e["sync_interval_hours"] == 12
    assert e["sync_minute"] == 17
    assert e["sync_on_dst"] is True
    assert e["dst_delay_minutes"] == 1
