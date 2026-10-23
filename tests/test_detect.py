"""Detect match: unknown Set or Reset on any group (no Home Assistant)."""

from __future__ import annotations

from b_logicx.detect import (
    DETECT_SETTLE_S,
    DETECT_WAIT_S,
    configured_bus_keys,
    detect_match,
    remember_detect_partner,
    shown_detect_frame,
)


def test_detect_wait_is_about_thirty_seconds():
    assert DETECT_WAIT_S == 30
    assert DETECT_SETTLE_S == 0.5


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


def test_cover_listen_keeps_set_and_ignores_reset():
    known = {(3, 1)}
    assert detect_match("Set", 3, 2, known, set_only=True) is True
    assert detect_match("Reset", 3, 2, known, set_only=True) is False
    assert detect_match("Set", 3, 1, known, set_only=True) is False
    assert detect_match("Reset", 3, 4, set()) is True


def test_shown_frame_prefers_the_set_from_the_same_press():
    reset = (3, 6, False)
    commanded = (3, 5, True)
    assert shown_detect_frame([reset, commanded]) == commanded
    assert shown_detect_frame([commanded, reset]) == commanded
    assert shown_detect_frame([reset]) == reset
    assert shown_detect_frame([]) is None


def test_partner_stash_keeps_a_later_set():
    known: set[tuple[int, int]] = set()
    stash = remember_detect_partner(None, "Reset", 3, 6, known)
    assert stash == (3, 6, False)
    stash = remember_detect_partner(stash, "Set", 3, 5, known)
    assert stash == (3, 5, True)
    assert remember_detect_partner(stash, "Reset", 3, 7, known) == (3, 5, True)
    assert remember_detect_partner(None, "Set", 2, 1, {(2, 1)}) is None
    assert remember_detect_partner(None, "Toggle", 2, 1, known) is None
    assert remember_detect_partner(None, "Set", 2, 1, known, own_echo=True) is None


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
