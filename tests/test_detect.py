"""Detect match: unknown Set or Reset on any group (no Home Assistant)."""

from __future__ import annotations

from b_logicx.detect import DETECT_WAIT_S, configured_bus_keys, detect_match


def test_detect_wait_is_about_thirty_seconds():
    assert DETECT_WAIT_S == 30


def test_unknown_set_and_reset_on_any_group_match():
    known: set[tuple[int, int]] = set()
    assert detect_match("Set", 2, 80, known) is True
    assert detect_match("Reset", 5, 12, known) is True
    assert detect_match("Set", 10, 4, known) is True


def test_known_address_cover_relay_and_own_echo_do_not_match():
    known = {(2, 80), (3, 5), (3, 6)}
    assert detect_match("Set", 2, 80, known) is False
    assert detect_match("Reset", 3, 5, known) is False
    assert detect_match("Set", 3, 6, known) is False
    assert detect_match("Set", 4, 1, known, own_echo=True) is False
    assert detect_match("Toggle", 2, 1, known) is False
    assert detect_match("Dimmer", 2, 1, known) is False


def test_configured_keys_include_both_cover_relays_and_moods():
    keys = configured_bus_keys(
        [
            {"type": "rlm", "group": 2, "address": 80},
            {
                "type": "shutter",
                "open_group": 3,
                "open_address": 5,
                "close_group": 3,
                "close_address": 6,
            },
            {
                "type": "sfeer",
                "group": 5,
                "moods": [{"name": "TV", "group": 5, "address": 221}],
            },
        ]
    )
    assert keys == {(2, 80), (3, 5), (3, 6), (5, 221)}
    assert detect_match("Set", 5, 221, keys) is False
    assert detect_match("Reset", 5, 12, keys) is True
