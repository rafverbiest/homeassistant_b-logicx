"""SoftM virtual status tracker unit tests."""

from __future__ import annotations

import pytest

from b_logicx.softm_tracker import SoftMConfig, SoftMTracker
from address_config import parse_addresses_yaml


def _tracker() -> SoftMTracker:
    t = SoftMTracker()
    t.configure(
        [
            SoftMConfig(10, 4, timer_seconds=0.05, default_state=False),
            SoftMConfig(10, 5, timer_seconds=None, default_state=True),
        ]
    )
    return t


def test_toggle_flip():
    t = _tracker()
    a = t.on_toggle(10, 4)
    assert a is not None and a.command == "Set"
    assert t.get_state(10, 4) is True
    a = t.on_toggle(10, 4)
    assert a is not None and a.command == "Reset"


def test_status_reply():
    t = _tracker()
    assert t.on_status(10, 5).command == "Set"  # default_state True
    assert t.on_status(10, 4).command == "Reset"


def test_timer_and_cancel_via_toggle():
    t = _tracker()
    result = t.on_timer(10, 4)
    assert result is not None
    action, secs = result
    assert action.command == "Set" and secs == 0.05
    assert (10, 4) in t.active_timers
    t.cancel_timer(10, 4)
    assert t.timer_expired(10, 4) is None  # cancelled


def test_timer_expire():
    t = _tracker()
    t.on_timer(10, 4)
    a = t.timer_expired(10, 4)
    assert a is not None and a.command == "Reset"
    assert t.get_state(10, 4) is False


def test_untracked_ignored():
    t = _tracker()
    assert t.on_toggle(2, 80) is None
    assert t.on_status(2, 80) is None


def test_yaml_softm_fields():
    content = """
addresses:
  - type: normal
    name: SoftM
    group: 10
    address: 4
    enable_softm_status_tracking: true
    softm_timer: 30
    persist_state: true
    default_state: false
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    e = entries[0]
    assert e["enable_softm_status_tracking"] is True
    assert e["softm_timer"] == 30.0
    assert e["check_status"] is False


def test_yaml_rejects_check_and_softm():
    content = """
addresses:
  - type: normal
    name: Bad
    group: 10
    address: 1
    check_status: true
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"
    assert entries == []


def test_yaml_rejects_timer_without_tracking():
    content = """
addresses:
  - type: normal
    name: Bad
    group: 10
    address: 1
    softm_timer: 10
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"


def test_yaml_rejects_softm_with_toggle():
    content = """
addresses:
  - type: normal
    name: Bad
    group: 10
    address: 1
    on_command: Toggle
    off_command: Toggle
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"
    assert entries == []


def test_yaml_rejects_softm_with_non_set_reset():
    content = """
addresses:
  - type: normal
    name: Bad
    group: 10
    address: 2
    on_command: Dimmer
    off_command: Reset
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"


def test_yaml_softm_defaults_to_set_reset():
    content = """
addresses:
  - type: normal
    name: SoftM
    group: 10
    address: 3
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert entries[0]["on_command"] == "Set"
    assert entries[0]["off_command"] == "Reset"


def test_set_reset_and_cancel_timer():
    t = _tracker()
    t.on_timer(10, 4)
    assert (10, 4) in t.active_timers
    t.cancel_timer(10, 4)
    t.on_set_reset(10, 4, True)
    assert t.get_state(10, 4) is True
    assert t.timer_expired(10, 4) is None


def test_same_subnet_filter():
    from bus_repeater import _same_subnet

    # Same /24 as a typical LAN gateway → accept
    assert _same_subnet("192.168.1.50", "192.168.1.10") is True
    # Different /24 → reject
    assert _same_subnet("10.0.0.5", "192.168.1.10") is False
    # Invalid IP → reject
    assert _same_subnet("not-an-ip", "192.168.1.10") is False
    # Loopback on the HA host → accept (not on the NWM LAN subnet)
    assert _same_subnet("127.0.0.1", "192.168.1.10") is True
    assert _same_subnet("::1", "192.168.1.10") is True
    assert _same_subnet("127.0.0.42", "10.0.0.1") is True
