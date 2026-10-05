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
  - type: softm
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
    assert e["type"] == "softm"
    assert e["enable_softm_status_tracking"] is True
    assert e["softm_timer"] == 30.0
    assert e["check_status"] is False


def test_yaml_rejects_check_and_softm():
    content = """
addresses:
  - type: softm
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
  - type: rlm
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
  - type: softm
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
  - type: softm
    name: Bad
    group: 10
    address: 2
    on_command: Dimmer
    off_command: Reset
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"


def test_softm_vsm_flag_can_stay_off():
    """Type softm stays a SoftM when a hardware status module already tracks it."""
    from const import is_softm_address

    content = """
addresses:
  - type: softm
    name: Hardware STA
    group: 10
    address: 9
    enable_softm_status_tracking: false
  - type: softm
    name: Virtual
    group: 10
    address: 10
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    hardware, virtual = entries
    assert hardware["type"] == "softm"
    assert hardware["enable_softm_status_tracking"] is False
    assert is_softm_address(hardware) is False
    assert virtual["type"] == "softm"
    assert virtual["enable_softm_status_tracking"] is True
    assert is_softm_address(virtual) is True

    from address_config import dump_addresses_yaml

    dumped = dump_addresses_yaml([hardware])
    assert "enable_softm_status_tracking: false" in dumped
    again, err2 = parse_addresses_yaml(dumped)
    assert err2 is None
    assert again[0]["type"] == "softm"
    assert again[0]["enable_softm_status_tracking"] is False


def test_softm_timer_rejected_when_vsm_off():
    content = """
addresses:
  - type: softm
    name: Bad
    group: 10
    address: 11
    enable_softm_status_tracking: false
    softm_timer: 20
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"
    assert entries == []


def test_yaml_softm_defaults_to_set_reset():
    content = """
addresses:
  - type: softm
    name: SoftM
    group: 10
    address: 3
    enable_softm_status_tracking: true
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert entries[0]["type"] == "softm"
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


def test_on_off_from_ha_state():
    from const import on_off_from_ha_state

    assert on_off_from_ha_state("on") is True
    assert on_off_from_ha_state("off") is False
    assert on_off_from_ha_state("unknown") is None
    assert on_off_from_ha_state(None) is None


def test_repeater_client_allowed():
    from bus_repeater import client_allowed, suggested_repeater_cidr

    # No configured CIDR → gateway /24
    assert client_allowed("192.168.1.50", "192.168.1.10") is True
    assert client_allowed("10.0.0.5", "192.168.1.10") is False
    assert client_allowed("not-an-ip", "192.168.1.10") is False
    # Loopback always allowed, even outside the typed subnet
    assert client_allowed("127.0.0.1", "192.168.1.10", "10.0.0.0/24") is True
    assert client_allowed("::1", "10.0.0.1", "192.168.50.0/24") is True
    # Typed CIDR replaces the /24 guess
    assert client_allowed("192.168.50.20", "10.1.1.1", "192.168.50.0/24") is True
    assert client_allowed("192.168.1.20", "192.168.1.10", "10.0.0.0/8") is False
    assert client_allowed("10.2.3.4", "192.168.1.10", "10.0.0.0/8") is True
    assert suggested_repeater_cidr("192.168.50.150") == "192.168.50.0/24"
    assert suggested_repeater_cidr("nwm.local") == ""
