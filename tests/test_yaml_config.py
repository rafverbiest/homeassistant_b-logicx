"""YAML address config parse tests (no Home Assistant)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from address_config import (
    dump_addresses_yaml,
    parse_addresses_yaml,
    parse_integration_settings,
)
from const import next_sfeer_group


ROOT = Path(__file__).resolve().parents[1]


def test_next_sfeer_group():
    assert next_sfeer_group() == 5
    assert next_sfeer_group({5}) == 6
    assert next_sfeer_group({5, 6, 7}) == 8
    # 10+ reserved
    assert next_sfeer_group(set(range(5, 10))) == 5  # wrap fallback when 5–9 full


def test_edge_cases_fixture():
    content = (Path(__file__).parent / "fixtures" / "edge_cases.yaml").read_text()
    entries, err = parse_addresses_yaml(content)
    assert err is None
    types = {e["type"] for e in entries}
    assert types == {"rlm", "shutter", "sfeer", "readonly"}
    sfeer = next(e for e in entries if e["type"] == "sfeer")
    assert len(sfeer["moods"]) == 2
    cover = next(e for e in entries if e["type"] == "shutter")
    assert cover["open_time"] == 0.15


def test_demo_site_yaml():
    """Larger fictional multi-type example (not a real installation)."""
    content = (ROOT / "examples" / "demo_site.yaml").read_text()
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert len(entries) >= 10
    types = {e["type"] for e in entries}
    assert {"rlm", "softm", "aud", "shutter", "sfeer", "readonly", "rtc"} <= types
    assert "normal" not in types
    # Example group conventions (fictional site layout)
    for e in entries:
        if e["type"] in ("rlm", "softm") and "Software" in e.get("name", ""):
            assert e["group"] == 10
        if e["type"] == "aud":
            assert e["group"] == 4
            assert e["source_1"] == "Radio"
        if e["type"] == "shutter":
            assert e["open_group"] == 3 and e["close_group"] == 3


def test_template_yaml():
    content = (
        ROOT / "custom_components" / "b_logicx" / "flow" / "template.yaml"
    ).read_text()
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert len(entries) >= 4


def test_invalid_yaml_syntax():
    entries, err = parse_addresses_yaml("addresses: [\n  - type: rlm\n    name: x\n")
    assert err == "invalid_yaml"
    assert entries == []


def test_missing_addresses_key():
    entries, err = parse_addresses_yaml("foo: 1\n")
    assert err == "invalid_format"


def test_wsm_yaml_defaults_and_roundtrip():
    entries, err = parse_addresses_yaml(
        "addresses:\n"
        "  - type: wsm\n"
        "    address: 12\n"
    )
    assert err is None
    assert entries[0]["name"] == "Wind sensor"
    assert entries[0]["group"] == 1
    assert entries[0]["address"] == 12
    assert entries[0]["check_status"] is False
    again, err = parse_addresses_yaml(dump_addresses_yaml(entries))
    assert err is None
    assert again[0]["type"] == "wsm"
    assert again[0]["check_status"] is False
    asked, err = parse_addresses_yaml(
        "addresses:\n"
        "  - type: wsm\n"
        "    name: Roof wind\n"
        "    group: 1\n"
        "    address: 12\n"
        "    check_status: true\n"
    )
    assert err is None
    assert asked[0]["check_status"] is True


def test_bm8_yaml_defaults_and_roundtrip():
    entries, err = parse_addresses_yaml(
        "addresses:\n"
        "  - type: bm8\n"
        "    address: 8\n"
    )
    assert err is None
    assert entries[0]["name"] == "Chime"
    assert entries[0]["group"] == 1
    assert entries[0]["address"] == 8
    assert "check_status" not in entries[0]
    again, err = parse_addresses_yaml(dump_addresses_yaml(entries))
    assert err is None
    assert again[0] == entries[0]
    named, err = parse_addresses_yaml(
        "addresses:\n"
        "  - type: bm8\n"
        "    name: Front door\n"
        "    group: 1\n"
        "    address: 8\n"
        "    check_status: true\n"
    )
    assert err is None
    assert named[0]["name"] == "Front door"
    assert "check_status" not in named[0]


def test_dimmer_yaml_defaults_and_roundtrip():
    content = """
addresses:
  - type: dimmer
    name: Table lamp
    group: 5
    address: 40
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert entries[0]["remembers_level"] is False
    assert entries[0]["check_status"] is False
    assert "default_level" not in entries[0]
    assert entries[0]["participates_in_moods"] is True
    again, err = parse_addresses_yaml(dump_addresses_yaml(entries))
    assert err is None
    assert "default_level" not in again[0]
    assert again[0]["participates_in_moods"] is True
    assert again[0]["check_status"] is False
    asked, err = parse_addresses_yaml(
        "addresses:\n"
        "  - type: dimmer\n"
        "    name: Table lamp\n"
        "    group: 5\n"
        "    address: 40\n"
        "    check_status: true\n"
    )
    assert err is None
    assert asked[0]["check_status"] is True


def test_dimmer_import_drops_a_default_level_key():
    content = """
addresses:
  - type: dimmer
    name: Table lamp
    group: 5
    address: 40
    default_level: 40
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert "default_level" not in entries[0]
    dumped = dump_addresses_yaml(
        [
            {
                "type": "dimmer",
                "name": "Table lamp",
                "group": 5,
                "address": 40,
                "remembers_level": False,
                "default_level": 40,
                "participates_in_moods": True,
            }
        ]
    )
    assert "default_level" not in dumped


def test_unknown_type():
    content = """
addresses:
  - type: not_a_thing
    name: X
    group: 1
    address: 1
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"


def test_sfeer_empty_moods_allowed():
    """Room may exist before moods are added (Add room for Sfeer)."""
    content = """
addresses:
  - type: sfeer
    name: Empty room
    group: 5
    check_status: false
    moods: []
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert len(entries) == 1
    assert entries[0]["group"] == 5
    assert entries[0]["moods"] == []


def test_sfeer_room_group_fills_moods():
    content = """
addresses:
  - type: sfeer
    name: Lounge
    group: 6
    moods:
      - name: Reading
        address: 221
      - name: Cinema
        address: 222
"""
    entries, err = parse_addresses_yaml(content)
    assert err is None
    moods = entries[0]["moods"]
    assert all(m["group"] == 6 for m in moods)
    assert moods[0]["address"] == 221


def test_shutter_requires_open_close():
    content = """
addresses:
  - type: shutter
    name: Broken
    open_group: 3
"""
    entries, err = parse_addresses_yaml(content)
    assert err == "invalid_format"


def test_dump_addresses_yaml_roundtrip():
    original = """
addresses:
  - type: rlm
    name: Lamp
    group: 2
    address: 41
    on_command: Set
    off_command: Reset
    check_status: true
  - type: shutter
    name: Rol
    open_group: 3
    open_address: 5
    close_group: 3
    close_address: 6
    open_time: 30
    close_time: 30
    check_status: false
  - type: sfeer
    name: Living
    group: 5
    check_status: true
    moods:
      - name: TV
        group: 5
        address: 221
"""
    entries, err = parse_addresses_yaml(original)
    assert err is None
    dumped = dump_addresses_yaml(
        entries,
        options={
            "softm_tracking_enabled": True,
            "bus_repeater_enabled": False,
            "bus_repeater_port": 10001,
        },
    )
    assert "softm_tracking_enabled: true" in dumped
    assert dumped.strip().startswith("#")
    assert "type: normal" not in dumped
    assert "type: rlm" in dumped
    assert re.search(
        r"type: rlm\n\s*name: Lamp\n\s*group: 2\n\s*address: 41\n",
        dumped,
    )
    assert "enable_softm_status_tracking" not in dumped.split("name: Rol")[0]
    again, err2 = parse_addresses_yaml(dumped)
    assert err2 is None
    assert len(again) == len(entries)
    assert {e["name"] for e in again} == {e["name"] for e in entries}
    assert re.search(
        r"type: shutter\n\s*name: Rol\n\s*open_group: 3\n\s*open_address: 5\n"
        r"\s*close_group: 3\n\s*close_address: 6\n",
        dumped,
    )
    assert re.search(
        r"type: sfeer\n\s*name: Living\n\s*group: 5\n\s*moods:\n",
        dumped,
    )


def test_type_normal_is_rejected():
    entries, err = parse_addresses_yaml(
        """
addresses:
  - type: normal
    name: Lamp
    group: 2
    address: 1
"""
    )
    assert err == "invalid_format"
    assert entries == []


def test_rlm_rejects_softm_flag():
    entries, err = parse_addresses_yaml(
        """
addresses:
  - type: rlm
    name: Bad
    group: 2
    address: 1
    enable_softm_status_tracking: true
"""
    )
    assert err == "invalid_format"
    assert entries == []


def test_aud_source_names_and_dump_order():
    entries, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    address: 3
    controller: bhs
    source_1: Radio
    source_3: ""
"""
    )
    assert err is None
    aud = entries[0]
    assert aud["type"] == "aud"
    assert aud["group"] == 4
    assert aud["address"] == 3
    assert aud["source_1"] == "Radio"
    assert aud["source_2"] == "Source 2"
    assert aud["source_3"] == "Source 3"
    dumped = dump_addresses_yaml(entries)
    assert re.search(
        r"type: aud\n\s*name: Living audio\n\s*group: 4\n\s*address: 3\n"
        r"\s*controller: bhs\n\s*source_1: Radio\n",
        dumped,
    )
    assert aud["controller"] == "bhs"
    assert "media_player" not in aud


def test_aud_controller_must_be_bhs_or_ha():
    for controller_line in ("", "    controller: both\n", "    controller:\n"):
        entries, err = parse_addresses_yaml(
            f"""
addresses:
  - type: aud
    name: Living audio
    address: 1
{controller_line}"""
        )
        assert err == "invalid_format"
        assert entries == []


def test_aud_ha_actions_are_checked():
    missing_stop, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    address: 1
    controller: ha
    media_player: media_player.living_room
"""
    )
    assert err == "invalid_format"
    assert missing_stop == []
    bad_step, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    address: 1
    controller: ha
    media_player: media_player.living_room
    stop_action: pause
    volume_step: 25
"""
    )
    assert err == "invalid_format"
    assert bad_step == []
    quiet_mute, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    address: 1
    controller: ha
    media_player: media_player.living_room
    stop_action: turn_off
"""
    )
    assert err is None
    assert "mute_action" not in quiet_mute[0]
    assert "volume_step" not in quiet_mute[0]


def test_aud_home_assistant_controller_requires_a_player():
    entries, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    group: 4
    address: 1
    controller: ha
"""
    )
    assert err == "invalid_format"
    assert entries == []
    entries, err = parse_addresses_yaml(
        """
addresses:
  - type: aud
    name: Living audio
    group: 4
    address: 1
    controller: ha
    media_player: media_player.living_room
    volume_step: 5
    stop_action: pause
    mute_action: volume
    turn_on_with_play: true
    source_1: Radio
"""
    )
    assert err is None
    aud = entries[0]
    assert aud["controller"] == "ha"
    assert aud["media_player"] == "media_player.living_room"
    assert aud["volume_step"] == 5
    assert aud["stop_action"] == "pause"
    assert aud["mute_action"] == "volume"
    assert aud["turn_on_with_play"] is True
    assert aud["source_1"] == "Radio"
    dumped = dump_addresses_yaml(entries)
    assert "controller: ha" in dumped
    assert "media_player: media_player.living_room" in dumped
    assert "volume_step: 5" in dumped
    assert "stop_action: pause" in dumped
    bhs = dict(aud)
    bhs["controller"] = "bhs"
    dumped_bhs = dump_addresses_yaml([bhs])
    assert "media_player" not in dumped_bhs
    assert "volume_step" not in dumped_bhs
    assert "stop_action" not in dumped_bhs
    assert "mute_action" not in dumped_bhs
    assert "turn_on_with_play" not in dumped_bhs


def test_export_writes_integration_settings_and_import_reads_them():
    dumped = dump_addresses_yaml(
        [
            {
                "type": "rlm",
                "name": "Lamp",
                "group": 2,
                "address": 1,
                "on_command": "Set",
                "off_command": "Reset",
            }
        ],
        options={"softm_tracking_enabled": True, "bus_repeater_enabled": True},
        allow_default="192.168.50.0/24",
    )
    assert "not applied" not in dumped
    assert "settings:" in dumped
    settings, err = parse_integration_settings(dumped)
    assert err is None
    assert settings == {
        "softm_tracking_enabled": True,
        "bus_repeater_enabled": True,
        "bus_repeater_port": 10001,
        "bus_repeater_allow": "192.168.50.0/24",
    }


def test_yaml_without_settings_leaves_them_unset():
    content = """
addresses:
  - type: rlm
    name: Lamp
    group: 2
    address: 1
"""
    settings, err = parse_integration_settings(content)
    assert err is None
    assert settings is None
    entries, addr_err = parse_addresses_yaml(content)
    assert addr_err is None
    assert entries[0]["name"] == "Lamp"


def test_partial_settings_and_invalid_subnet():
    partial = """
settings:
  bus_repeater_enabled: false
addresses:
  - type: rlm
    name: Lamp
    group: 2
    address: 1
"""
    settings, err = parse_integration_settings(partial)
    assert err is None
    assert settings == {"bus_repeater_enabled": False}

    bad = """
settings:
  bus_repeater_allow: not-a-network
addresses:
  - type: rlm
    name: Lamp
    group: 2
    address: 1
"""
    settings, err = parse_integration_settings(bad)
    assert settings is None
    assert err == "invalid_subnet"

    bad_port = """
settings:
  bus_repeater_port: 0
addresses:
  - type: rlm
    name: Lamp
    group: 2
    address: 1
"""
    settings, err = parse_integration_settings(bad_port)
    assert settings is None
    assert err == "invalid_format"
