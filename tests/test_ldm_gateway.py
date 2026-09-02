"""LDM request sequence against FakeGateway (connection layer)."""

from __future__ import annotations

import asyncio

import pytest

from b_logicx import BLXConnection
from b_logicx.measure import value_frame_to_raw


@pytest.mark.asyncio
async def test_ldm_request_tx_sequence(fake_gateway):
    """Client should send Data 0.2 then Select g.a for an LDM poll."""
    gw = fake_gateway

    async def handler(gw_self, event):
        # After Select, emit Value + System as real LDM would
        if event.command == "Select" and event.group == 1 and event.address == 23:
            await gw_self.emit("Value", 3, 211)
            await gw_self.emit("System", 1, 23)
        # Data 0.2 is the first half of the request — ignore
        if event.command == "Data":
            return

    gw.on_command(handler)

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    got = []

    async def collect():
        async for ev in conn.events():
            got.append(ev)
            if len(got) >= 2:
                break

    t = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    await conn.send("Data", 0, 2)
    await asyncio.sleep(0.01)
    await conn.send("Select", 1, 23)
    await asyncio.wait_for(t, timeout=2.0)

    assert [(e.command, e.group, e.address) for e in gw.rx_log[-2:]] == [
        ("Data", 0, 2),
        ("Select", 1, 23),
    ]
    assert got[0].command == "Value"
    # Value 3.211 → packed12 = (3<<8)|211 = 979
    assert value_frame_to_raw(got[0].group, got[0].address) == 979
    assert got[1].command == "System"
    assert (got[1].group, got[1].address) == (1, 23)

    await conn.close()


@pytest.mark.asyncio
async def test_status_timeout_no_reply(fake_gateway):
    """Status with drop: client never gets Set/Reset (non-responsive member)."""
    gw = fake_gateway
    gw.drop_status_for.add((2, 50))

    conn = BLXConnection("127.0.0.1", gw.bound_port)
    await conn.connect()

    got = []

    async def collect():
        try:
            async with asyncio.timeout(0.4):
                async for ev in conn.events():
                    got.append(ev)
        except TimeoutError:
            pass

    t = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    await conn.send("Status", 2, 50)
    await t
    assert got == []
    assert any(e.command == "Status" for e in gw.rx_log)

    await conn.close()
