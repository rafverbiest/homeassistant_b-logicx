"""Hub serialises Status / LDM / TSM on one request lock.

Regression for: Status 2.41 wait interrupted by LDM Data 0.2 (separate
_status_lock vs _tx_lock in 0.8.1) so Set/Reset never arrives and the Status
waiter times out.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_DIR = ROOT / "custom_components" / "b_logicx"


def _import_hub():
    """Load integration hub without Home Assistant installed."""
    if "custom_components.b_logicx.hub" in sys.modules:
        return sys.modules["custom_components.b_logicx.hub"]

    if "custom_components" not in sys.modules:
        cc = types.ModuleType("custom_components")
        cc.__path__ = [str(ROOT / "custom_components")]
        sys.modules["custom_components"] = cc

    if "custom_components.b_logicx" not in sys.modules:
        pkg = types.ModuleType("custom_components.b_logicx")
        pkg.__path__ = [str(INTEGRATION_DIR)]
        sys.modules["custom_components.b_logicx"] = pkg

    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        ha_core = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # noqa: N801 — mirror HA name
            pass

        ha_core.HomeAssistant = HomeAssistant
        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.core"] = ha_core

    if str(INTEGRATION_DIR) not in sys.path:
        sys.path.insert(0, str(INTEGRATION_DIR))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from custom_components.b_logicx import hub as hub_mod  # noqa: WPS433

    return hub_mod


class _FakeHass:
    def async_create_background_task(self, coro, name=None):
        return asyncio.create_task(coro)


@pytest.mark.asyncio
async def test_status_blocks_ldm_tx_until_set_reset(fake_gateway):
    """LDM must not TX Data while a Status waiter is still open."""
    hub_mod = _import_hub()
    gw = fake_gateway
    gw.set_state(2, 41, False)  # Reset reply
    # Slow Status reply so LDM has time to race if the lock is wrong
    gw.status_delay = 0.25

    ldm_replied = asyncio.Event()

    async def handler(gw_self, event):
        if event.command == "Select" and (event.group, event.address) == (1, 23):
            await gw_self.emit("Value", 3, 242)
            await gw_self.emit("System", 1, 23)
            ldm_replied.set()
            return
        if event.command == "Data":
            return
        if event.command == "Status":
            key = (event.group, event.address)
            if key in gw_self.drop_status_for:
                return
            if gw_self.status_delay:
                await asyncio.sleep(gw_self.status_delay)
            on = gw_self.state.get(key, False)
            await gw_self.emit("Set" if on else "Reset", event.group, event.address)
            return

    gw.on_command(handler)

    hub = hub_mod.BLogicxHub(_FakeHass(), "127.0.0.1", gw.bound_port)
    await hub.async_start()
    # Register LDM key so System commits the reading
    hub.register_ldm(1, 23, lambda _r: None)

    status_task = asyncio.create_task(hub.async_request_status(2, 41))
    await asyncio.sleep(0.02)  # Status TX should be out, still waiting for Reset
    ldm_task = asyncio.create_task(hub.async_request_ldm(1, 23))

    is_on = await asyncio.wait_for(status_task, timeout=3.0)
    reading = await asyncio.wait_for(ldm_task, timeout=3.0)

    assert is_on is False
    assert reading is not None
    assert reading.raw == ((3 << 8) | 242)

    # Client TX on the wire (gateway rx_log): Status must finish before LDM Data.
    # With the old dual-lock bug this was Status, Data, Select (Data mid-wait).
    cmds = [(e.command, e.group, e.address) for e in gw.rx_log]
    assert cmds == [
        ("Status", 2, 41),
        ("Data", 0, 2),
        ("Select", 1, 23),
    ], cmds

    await hub.async_close()


@pytest.mark.asyncio
async def test_status_2_41_reset_not_lost_with_concurrent_ldm(fake_gateway):
    """Exact user scenario: Status 2.41 + concurrent LDM 1.23 → Reset still matches."""
    hub_mod = _import_hub()
    gw = fake_gateway
    gw.set_state(2, 41, False)
    gw.status_delay = 0.15  # Reset arrives after LDM would have raced

    async def handler(gw_self, event):
        if event.command == "Select" and (event.group, event.address) == (1, 23):
            await gw_self.emit("Value", 3, 242)
            await gw_self.emit("System", 1, 23)
            return
        if event.command == "Data":
            return
        if event.command == "Status":
            if gw_self.status_delay:
                await asyncio.sleep(gw_self.status_delay)
            on = gw_self.state.get((event.group, event.address), False)
            await gw_self.emit("Set" if on else "Reset", event.group, event.address)

    gw.on_command(handler)

    hub = hub_mod.BLogicxHub(_FakeHass(), "127.0.0.1", gw.bound_port)
    await hub.async_start()
    hub.register_ldm(1, 23, lambda _r: None)

    st, ldm = await asyncio.gather(
        hub.async_request_status(2, 41),
        hub.async_request_ldm(1, 23),
    )
    assert st is False
    assert ldm is not None

    await hub.async_close()
