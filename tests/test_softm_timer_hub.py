"""SoftM Timer must survive own Set/Status reply echoes (hub regression)."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from b_logicx.models import BLXEvent
from b_logicx.softm_tracker import SoftMConfig

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_DIR = ROOT / "custom_components" / "b_logicx"


def _import_hub():
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

        class HomeAssistant:  # noqa: N801
            pass

        ha_core.HomeAssistant = HomeAssistant
        sys.modules["homeassistant"] = ha
        sys.modules["homeassistant.core"] = ha_core

    if str(INTEGRATION_DIR) not in sys.path:
        sys.path.insert(0, str(INTEGRATION_DIR))

    from custom_components.b_logicx import hub as hub_mod  # noqa: WPS433

    return hub_mod


class _FakeHass:
    def async_create_background_task(self, coro, name=None):
        return asyncio.create_task(coro)


def _softm_hub(timer_seconds: float = 0.08):
    hub_mod = _import_hub()
    hub = hub_mod.BLogicxHub(_FakeHass(), "127.0.0.1", 9)
    hub.configure_softm_tracking(
        True,
        [SoftMConfig(10, 4, timer_seconds=timer_seconds, default_state=False)],
    )
    sent: list[str] = []

    async def fake_send(command: str, group: int, address: int) -> None:
        sent.append(command)

    hub.async_send = fake_send  # type: ignore[method-assign]
    return hub, sent


@pytest.mark.asyncio
async def test_softm_timer_survives_set_echo_and_status():
    """Timer → own Set echo + Status reply must still auto-Reset."""
    hub, sent = _softm_hub(0.08)

    await hub._handle_softm_event(BLXEvent(command="Timer", group=10, address=4, raw=b"\x00\x00"))
    assert sent == ["Set"]
    assert (10, 4) in hub._softm.active_timers
    assert (10, 4) in hub._softm_timer_tasks

    # Own Set echo (gateway reflected SoftM TX)
    await hub._handle_softm_event(BLXEvent(command="Set", group=10, address=4, raw=b"\x00\x00"))
    assert (10, 4) in hub._softm.active_timers
    task = hub._softm_timer_tasks[(10, 4)]
    assert not task.cancelled()

    # Status mid-timer: reply Set, must not cancel countdown
    await hub._handle_softm_event(BLXEvent(command="Status", group=10, address=4, raw=b"\x00\x00"))
    assert sent[-1] == "Set"
    await hub._handle_softm_event(BLXEvent(command="Set", group=10, address=4, raw=b"\x00\x00"))
    assert (10, 4) in hub._softm.active_timers
    assert not task.cancelled()

    await asyncio.sleep(0.15)
    assert "Reset" in sent
    assert hub._softm.get_state(10, 4) is False
    hub._softm_own_emit.clear()


@pytest.mark.asyncio
async def test_softm_external_reset_cancels_timer():
    hub, sent = _softm_hub(1.0)

    await hub._handle_softm_event(BLXEvent(command="Timer", group=10, address=4, raw=b"\x00\x00"))
    assert sent == ["Set"]
    assert (10, 4) in hub._softm.active_timers

    # Consume own Set echo first (as on a reflecting gateway)
    await hub._handle_softm_event(BLXEvent(command="Set", group=10, address=4, raw=b"\x00\x00"))
    assert (10, 4) in hub._softm.active_timers

    # External Reset (no own-emit mark)
    await hub._handle_softm_event(BLXEvent(command="Reset", group=10, address=4, raw=b"\x00\x00"))
    assert (10, 4) not in hub._softm.active_timers
    task = hub._softm_timer_tasks.get((10, 4))
    assert task is None or task.cancelled() or task.done()
    hub._softm_own_emit.clear()
