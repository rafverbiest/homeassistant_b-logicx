"""YAML address config parse tests (no Home Assistant)."""

from __future__ import annotations

from pathlib import Path

import pytest

from address_config import parse_addresses_yaml
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
    assert types == {"normal", "shutter", "sfeer", "readonly"}
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
    assert {"normal", "shutter", "sfeer", "readonly", "rtc"} <= types
    # Example group conventions (fictional site layout)
    for e in entries:
        if e["type"] == "normal" and "Software" in e.get("name", ""):
            assert e["group"] == 10
        if e["type"] == "shutter":
            assert e["open_group"] == 3 and e["close_group"] == 3


def test_template_yaml():
    content = (
        ROOT / "custom_components" / "b_logicx" / "template.yaml"
    ).read_text()
    entries, err = parse_addresses_yaml(content)
    assert err is None
    assert len(entries) >= 4


def test_invalid_yaml_syntax():
    entries, err = parse_addresses_yaml("addresses: [\n  - type: normal\n    name: x\n")
    assert err == "invalid_yaml"
    assert entries == []


def test_missing_addresses_key():
    entries, err = parse_addresses_yaml("foo: 1\n")
    assert err == "invalid_format"


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
