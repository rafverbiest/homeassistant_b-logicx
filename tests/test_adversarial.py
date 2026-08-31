"""Adversarial FakeGateway scenarios — try to confuse the client."""

from __future__ import annotations

import asyncio
import logging

import pytest

from b_logicx import BLXConnection
from b_logicx.connection import BLXConnection as BLXConnectionClass


async def _collect_matching(conn, n, *, commands=None, timeout=3.0):
    """Collect up to *n* events, optionally filtered by command name(s)."""
    got = []
    async for ev in conn.events():
        if commands is None or ev.command in commands:
            got.append(ev)
            if len(got) >= n:
                break
    return got


@pytest.mark.asyncio
async def test_rapid_status_serial_replies(fake_gateway):
    """Many Status queries back-to-back; framing must stay aligned."""
    gw = fake_gateway
    addrs = [(2, i) for i in range(1, 11)]
    for g, a in addrs:
        gw.set_state(g, a, a % 2 == 0)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    t = asyncio.create_task(
        _collect_matching(conn, 10, commands=("Set", "Reset"))
    )
    await asyncio.sleep(0.05)
    for g, a in addrs:
        await conn.send("Status", g, a)
    got = await asyncio.wait_for(t, timeout=3.0)

    assert len(got) == 10
    for i, (g, a) in enumerate(addrs):
        assert got[i].group == g and got[i].address == a
        expect = "Set" if a % 2 == 0 else "Reset"
        assert got[i].command == expect, (i, got[i])

    await conn.close()


@pytest.mark.asyncio
async def test_interleaved_unsolicited_during_status(fake_gateway):
    """Unsolicited traffic between Status and reply must not desync pairing."""
    gw = fake_gateway
    gw.set_state(2, 80, True)

    # Custom: after Status 2.80, first inject noise then reply
    async def tricky(gw_self, event):
        if event.command == "Status" and event.address == 80:
            await gw_self.emit("Set", 9, 99)  # noise
            await asyncio.sleep(0.02)
            await gw_self.emit("Set", 2, 80)  # real reply
            return
        # default-ish for other commands
        if event.command == "Status":
            await gw_self.emit(
                "Set" if gw_self.state.get((event.group, event.address)) else "Reset",
                event.group,
                event.address,
            )

    gw.on_command(tricky)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 2))
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 80)
    got = await asyncio.wait_for(t, timeout=2.0)

    assert got[0].group == 9 and got[0].address == 99
    assert got[1].group == 2 and got[1].address == 80 and got[1].command == "Set"
    await conn.close()


@pytest.mark.asyncio
async def test_status_then_scripted_burst(fake_gateway):
    """After Status round-trip, a burst of predefined frames stays decoded."""
    gw = fake_gateway
    gw.set_state(1, 5, False)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 6))
    await asyncio.sleep(0.05)
    await conn.send("Status", 1, 5)
    await asyncio.sleep(0.08)
    await gw.emit_sequence(
        [
            ("Set", 2, 17),
            ("Reset", 2, 17),
            ("Dimmer", 5, 221),  # raw emit of Dimmer (unusual unsolicited)
            ("Set", 5, 221),
            ("Reset", 5, 222),
        ],
        delay=0.01,
    )
    got = await asyncio.wait_for(t, timeout=2.0)
    tuples = [(e.command, e.group, e.address) for e in got]

    assert tuples[0] == ("Reset", 1, 5)
    assert ("Set", 2, 17) in tuples
    assert ("Set", 5, 221) in tuples
    # No garbage high groups from framing slip
    for _cmd, g, _a in tuples:
        assert 0 <= g <= 15

    await conn.close()


# ---------------------------------------------------------------------------
# Program decoys: payload frames that look like genuine Status replies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_program_payload_decoy_as_first_frame(fake_gateway):
    """Program + Set matching a pending Status as payload #1 must be skipped.

    Real-world trap: programming traffic can contain bytes that decode as a
    normal command for the address we just Status'd. Out of context it looks
    like the reply — with skip_programming it must still be discarded.
    """
    gw = fake_gateway
    gw.set_state(2, 80, True)

    async def handler(gw_self, event):
        if event.command == "Status" and event.address == 80:
            # Decoy Set 2.80 is *first* payload after Program
            await gw_self.emit_program_payload(
                [("Set", 2, 80), ("Value", 2, 145)],
                delay=0.005,
            )
            await asyncio.sleep(0.02)
            # Genuine Status reply after programming sequence ends
            await gw_self.emit("Set", 2, 80)
            return
        if event.command == "Status":
            is_on = gw_self.state.get((event.group, event.address), False)
            await gw_self.emit("Set" if is_on else "Reset", event.group, event.address)

    gw.on_command(handler)

    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 1))
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 80)
    got = await asyncio.wait_for(t, timeout=2.0)

    # Exactly one visible Set 2.80 — the real reply, not the Program decoy
    assert len(got) == 1
    assert got[0].command == "Set" and got[0].group == 2 and got[0].address == 80

    # Drain briefly: no second Set should appear from the decoy
    extra = []

    async def drain():
        async for ev in conn.events():
            extra.append(ev)
            if len(extra) >= 1:
                break

    drain_t = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(drain_t, timeout=0.15)
    except TimeoutError:
        drain_t.cancel()
    assert extra == [], f"unexpected events after real reply: {extra}"

    await conn.close()


@pytest.mark.asyncio
async def test_program_payload_decoy_as_second_frame(fake_gateway):
    """Program + junk + Set matching Status as payload #2 must be skipped."""
    gw = fake_gateway
    gw.set_state(2, 41, False)  # real reply will be Reset

    async def handler(gw_self, event):
        if event.command == "Status" and event.address == 41:
            # Decoy looks like "on" but device is off — wrong AND must be skipped
            await gw_self.emit_program_payload(
                [("Data", 15, 82), ("Set", 2, 41)],
                delay=0.005,
            )
            await asyncio.sleep(0.02)
            await gw_self.emit("Reset", 2, 41)
            return
        if event.command == "Status":
            is_on = gw_self.state.get((event.group, event.address), False)
            await gw_self.emit("Set" if is_on else "Reset", event.group, event.address)

    gw.on_command(handler)

    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 1, commands=("Set", "Reset")))
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 41)
    got = await asyncio.wait_for(t, timeout=2.0)

    assert len(got) == 1
    assert got[0].command == "Reset"
    assert got[0].group == 2 and got[0].address == 41
    # If the decoy Set had leaked through, we'd see Set instead of / before Reset
    await conn.close()


@pytest.mark.asyncio
async def test_program_decoy_does_not_leak_with_skip_disabled_contrast(fake_gateway):
    """With skip_programming=False, Program + decoy payload *are* visible.

    Contrast test: proves the decoy frames are real wire traffic; only the
    default skip filter hides them.
    """
    gw = fake_gateway
    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=False)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 4))
    await asyncio.sleep(0.05)
    await gw.emit_program_payload([("Set", 2, 80), ("Reset", 2, 80)])
    await gw.emit("Toggle", 3, 1)
    got = await asyncio.wait_for(t, timeout=2.0)

    cmds = [(e.command, e.group, e.address) for e in got]
    assert cmds[0] == ("Program", 0, 0)
    assert cmds[1] == ("Set", 2, 80)
    assert cmds[2] == ("Reset", 2, 80)
    assert cmds[3] == ("Toggle", 3, 1)
    await conn.close()


# ---------------------------------------------------------------------------
# Program payload timeout (production default is 10s; tests use a short value)
# ---------------------------------------------------------------------------

# Wall-clock wait for the shortened deadline. Keep modest so the suite stays
# fast; still exercises the same branch as the real 10s timeout.
_TEST_PROGRAM_TIMEOUT = 0.2
_TEST_PROGRAM_WAIT = 0.35  # > _TEST_PROGRAM_TIMEOUT with a little margin


@pytest.mark.asyncio
async def test_program_payload_timeout_delivers_late_frame(
    fake_gateway, monkeypatch, caplog
):
    """If the two Program payload frames never arrive, resume normal delivery.

    Production uses PROGRAM_PAYLOAD_TIMEOUT = 10s. We monkeypatch a short
    timeout so this stays a sub-second test while hitting the same code path.
    A late Set after the deadline must be delivered (not eaten as payload).
    """
    monkeypatch.setattr(
        BLXConnectionClass, "PROGRAM_PAYLOAD_TIMEOUT", _TEST_PROGRAM_TIMEOUT
    )

    gw = fake_gateway
    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 1))
    await asyncio.sleep(0.05)

    with caplog.at_level(logging.WARNING, logger="b_logicx.connection"):
        await gw.emit("Program", 0, 0)
        # No payload datagrams — wait past the (shortened) deadline
        await asyncio.sleep(_TEST_PROGRAM_WAIT)
        await gw.emit("Set", 2, 7)

        got = await asyncio.wait_for(t, timeout=2.0)

    assert len(got) == 1
    assert got[0].command == "Set" and got[0].group == 2 and got[0].address == 7
    assert any(
        "Timed out waiting for Program payload" in r.message for r in caplog.records
    ), f"expected timeout warning, got: {[r.message for r in caplog.records]}"

    await conn.close()


@pytest.mark.asyncio
async def test_program_payload_timeout_after_partial_skip(
    fake_gateway, monkeypatch, caplog
):
    """One payload arrives in time (skipped); a late second frame is delivered.

    skip_count goes 2 → 1 after the first payload. When the deadline expires
    before the second payload, the next datagram falls through as a normal event.
    """
    monkeypatch.setattr(
        BLXConnectionClass, "PROGRAM_PAYLOAD_TIMEOUT", _TEST_PROGRAM_TIMEOUT
    )

    gw = fake_gateway
    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    t = asyncio.create_task(_collect_matching(conn, 1))
    await asyncio.sleep(0.05)

    with caplog.at_level(logging.WARNING, logger="b_logicx.connection"):
        await gw.emit("Program", 0, 0)
        await gw.emit("Data", 15, 82)  # within window → skipped (count 2→1)
        await asyncio.sleep(_TEST_PROGRAM_WAIT)
        # Looks like it could be payload #2, but deadline has passed
        await gw.emit("Set", 2, 17)

        got = await asyncio.wait_for(t, timeout=2.0)

    assert len(got) == 1
    assert got[0].command == "Set" and got[0].address == 17
    assert any(
        "Timed out waiting for Program payload" in r.message for r in caplog.records
    )

    await conn.close()


# ---------------------------------------------------------------------------
# Light-sensor Select / Value noise (real bus traffic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_light_sensor_select_value_between_status(fake_gateway):
    """Select + Value pairs mid-Status must not break framing or replies.

    Real bus often shows ``Select 1.23`` then ``Value 2.145`` when light
    levels change. Integration does not act on them yet; library must still
    deliver framed events and Status Set/Reset must remain correct.
    """
    gw = fake_gateway
    addrs = [(2, 10), (2, 11), (2, 12)]
    for g, a in addrs:
        gw.set_state(g, a, a == 11)

    # After each Status, inject light-sensor noise then the real reply
    async def handler(gw_self, event):
        if event.command != "Status":
            return
        key = (event.group, event.address)
        await gw_self.emit_light_sensor(
            select=(1, 23),
            value=(2, 145),
            delay=0.005,
        )
        is_on = gw_self.state.get(key, False)
        await gw_self.emit("Set" if is_on else "Reset", event.group, event.address)

    gw.on_command(handler)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    all_events = []

    async def collect_all(n_status_replies):
        replies = 0
        async for ev in conn.events():
            all_events.append(ev)
            if ev.command in ("Set", "Reset") and (ev.group, ev.address) in addrs:
                replies += 1
                if replies >= n_status_replies:
                    break

    t = asyncio.create_task(collect_all(3))
    await asyncio.sleep(0.05)
    for g, a in addrs:
        await conn.send("Status", g, a)
        await asyncio.sleep(0.02)
    await asyncio.wait_for(t, timeout=3.0)

    # Light-sensor traffic visible on the bus stream
    pairs = [(e.command, e.group, e.address) for e in all_events]
    assert ("Select", 1, 23) in pairs
    assert ("Value", 2, 145) in pairs

    # Status answers still correct and in order
    status_replies = [
        e
        for e in all_events
        if e.command in ("Set", "Reset") and (e.group, e.address) in addrs
    ]
    assert len(status_replies) == 3
    assert status_replies[0].command == "Reset" and status_replies[0].address == 10
    assert status_replies[1].command == "Set" and status_replies[1].address == 11
    assert status_replies[2].command == "Reset" and status_replies[2].address == 12

    # Framing sanity
    for e in all_events:
        assert 0 <= e.group <= 15
        assert 0 <= e.address <= 255

    await conn.close()


@pytest.mark.asyncio
async def test_rapid_status_with_light_and_program_noise(fake_gateway):
    """Combine rapid Status with occasional Program decoys and light sensors."""
    gw = fake_gateway
    addrs = [(2, i) for i in range(1, 9)]
    for g, a in addrs:
        gw.set_state(g, a, a % 2 == 0)

    status_n = 0

    async def handler(gw_self, event):
        nonlocal status_n
        if event.command != "Status":
            return
        status_n += 1
        g, a = event.group, event.address
        key = (g, a)

        # Every 3rd Status: Program with decoy reply as first payload
        if status_n % 3 == 0:
            decoy = "Set" if gw_self.state.get(key, False) else "Reset"
            await gw_self.emit_program_payload(
                [(decoy, g, a), ("Data", 4, 82)],
                delay=0.002,
            )
        # Every 2nd Status: light-sensor pair in the middle
        if status_n % 2 == 0:
            await gw_self.emit_light_sensor(delay=0.002)

        is_on = gw_self.state.get(key, False)
        await gw_self.emit("Set" if is_on else "Reset", g, a)

    gw.on_command(handler)

    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    t = asyncio.create_task(
        _collect_matching(conn, 8, commands=("Set", "Reset"))
    )
    # Also sample that Select/Value still surface (not Program-skipped)
    noise = []

    async def watch_noise():
        async for ev in conn.events():
            if ev.command in ("Select", "Value", "Program"):
                noise.append(ev)

    noise_t = asyncio.create_task(watch_noise())
    await asyncio.sleep(0.05)
    for g, a in addrs:
        await conn.send("Status", g, a)
        await asyncio.sleep(0.01)

    got = await asyncio.wait_for(t, timeout=4.0)
    noise_t.cancel()
    try:
        await noise_t
    except asyncio.CancelledError:
        pass

    assert len(got) == 8
    for i, (g, a) in enumerate(addrs):
        assert got[i].group == g and got[i].address == a
        expect = "Set" if a % 2 == 0 else "Reset"
        assert got[i].command == expect, (i, got[i], "decoy may have leaked")

    # Light sensors should have been seen; Program must never surface
    assert any(e.command == "Select" for e in noise)
    assert any(e.command == "Value" for e in noise)
    assert not any(e.command == "Program" for e in noise)

    await conn.close()
