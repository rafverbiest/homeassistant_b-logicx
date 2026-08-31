"""Encode/decode and basic connection tests against FakeGateway."""

from __future__ import annotations

import asyncio

import pytest

from b_logicx import BLXConnection, decode_datagram, encode_datagram
from b_logicx.const import COMMAND_NAMES


@pytest.mark.parametrize(
    "command,group,address",
    [
        ("Set", 2, 80),
        ("Reset", 2, 41),
        ("Toggle", 3, 5),
        ("Status", 5, 221),
        ("Dimmer", 5, 222),
        ("Program", 0, 0),
    ],
)
def test_encode_decode_roundtrip(command, group, address):
    raw = encode_datagram(command, group, address)
    assert len(raw) == 2
    ev = decode_datagram(raw)
    assert ev.command == command
    assert ev.group == group
    assert ev.address == address


def test_all_command_codes_roundtrip():
    for name, code in COMMAND_NAMES.items():
        raw = encode_datagram(name, code % 16, code)
        ev = decode_datagram(raw)
        assert ev.command == name


@pytest.mark.asyncio
async def test_status_reply_set_reset(fake_gateway):
    gw = fake_gateway
    gw.set_state(2, 17, True)
    gw.set_state(2, 41, False)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    events = []

    async def collect():
        async for ev in conn.events():
            events.append(ev)
            if len(events) >= 2:
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 17)
    await conn.send("Status", 2, 41)
    await asyncio.wait_for(task, timeout=2.0)

    assert events[0].command == "Set" and events[0].group == 2 and events[0].address == 17
    assert events[1].command == "Reset" and events[1].address == 41

    await conn.close()


@pytest.mark.asyncio
async def test_two_subscribers_same_stream(fake_gateway):
    """Single reader: two events() consumers see the same Status replies."""
    gw = fake_gateway
    gw.set_state(2, 10, True)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    a, b = [], []

    async def take(dest, n):
        async for ev in conn.events():
            dest.append(ev)
            if len(dest) >= n:
                break

    t1 = asyncio.create_task(take(a, 1))
    t2 = asyncio.create_task(take(b, 1))
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 10)
    await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)

    assert len(a) == 1 and len(b) == 1
    assert a[0].command == b[0].command == "Set"
    assert a[0].address == b[0].address == 10

    await conn.close()


@pytest.mark.asyncio
async def test_drop_status_does_not_reply(fake_gateway):
    gw = fake_gateway
    gw.set_state(2, 99, True)
    gw.drop_status_for.add((2, 99))

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    got = []

    async def take_one():
        async for ev in conn.events():
            got.append(ev)
            break

    task = asyncio.create_task(take_one())
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 99)
    # Should time out — no reply
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=0.3)

    assert got == []
    await conn.close()


@pytest.mark.asyncio
async def test_delayed_status_still_arrives(fake_gateway):
    gw = fake_gateway
    gw.set_state(2, 50, False)
    gw.status_delay = 0.15

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    got = []

    async def take_one():
        async for ev in conn.events():
            got.append(ev)
            break

    task = asyncio.create_task(take_one())
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 50)
    await asyncio.wait_for(task, timeout=2.0)
    assert got[0].command == "Reset"
    await conn.close()


@pytest.mark.asyncio
async def test_program_skip_hides_payload(fake_gateway):
    """Client with skip_programming should not yield Program + next 2 frames."""
    gw = fake_gateway
    conn = BLXConnection("127.0.0.1", gw.bound_port, skip_programming=True)
    await conn.connect()

    visible = []

    async def collect(n_timeout=1.0):
        try:
            async with asyncio.timeout(n_timeout):
                async for ev in conn.events():
                    visible.append(ev)
                    if len(visible) >= 1 and visible[0].command == "Set":
                        break
        except TimeoutError:
            pass

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    # Inject Program + 2 junk + a real Set
    await gw.emit("Program", 0, 0)
    await gw.emit("Data", 15, 82)  # would look like garbage if not skipped
    await gw.emit("Data", 4, 82)
    await gw.emit("Set", 2, 7)
    await asyncio.wait_for(task, timeout=2.0)

    assert len(visible) == 1
    assert visible[0].command == "Set"
    assert visible[0].group == 2 and visible[0].address == 7
    await conn.close()


@pytest.mark.asyncio
async def test_sfeer_dimmer_exclusive(fake_gateway):
    gw = fake_gateway
    gw.register_sfeer_mood("Living", 5, 221)
    gw.register_sfeer_mood("Living", 5, 222)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    async def collect(n):
        out = []
        async for ev in conn.events():
            out.append(ev)
            if len(out) >= n:
                break
        return out

    t = asyncio.create_task(collect(1))
    await asyncio.sleep(0.05)
    await conn.send("Dimmer", 5, 221)
    batch1 = await asyncio.wait_for(t, timeout=2.0)
    assert batch1[-1].command == "Set" and batch1[-1].address == 221

    t = asyncio.create_task(collect(2))  # Reset previous + Set new
    await asyncio.sleep(0.05)
    await conn.send("Dimmer", 5, 222)
    batch2 = await asyncio.wait_for(t, timeout=2.0)
    cmds = [(e.command, e.address) for e in batch2]
    assert ("Reset", 221) in cmds
    assert ("Set", 222) in cmds

    await conn.close()


@pytest.mark.asyncio
async def test_unsolicited_sequence_after_status(fake_gateway):
    """Status, short wait, then scripted bus noise — client must stay framed."""
    gw = fake_gateway
    gw.set_state(2, 2, False)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    got = []

    async def collect(n):
        async for ev in conn.events():
            got.append(ev)
            if len(got) >= n:
                break

    t = asyncio.create_task(collect(4))
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 2)
    await asyncio.sleep(0.05)
    await gw.emit_sequence(
        [("Set", 2, 3), ("Reset", 2, 3), ("Set", 10, 4)],
        delay=0.02,
    )
    await asyncio.wait_for(t, timeout=2.0)

    assert got[0].command == "Reset" and got[0].address == 2
    assert got[1].command == "Set" and got[1].address == 3
    assert got[2].command == "Reset" and got[2].address == 3
    assert got[3].command == "Set" and got[3].group == 10

    await conn.close()
