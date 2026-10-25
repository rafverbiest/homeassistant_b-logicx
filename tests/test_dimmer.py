"""Dimmer level pairing and Sfeer on/off, without Home Assistant."""

from __future__ import annotations

from b_logicx.dimmer import (
    DIMMER_STOP_ADDRESS,
    DIMMER_TAP_WINDOW_S,
    DimmerBus,
    DimmerConfig,
    DimmerView,
    brightness_to_percent,
    dimmer_toggle_frames,
    percent_to_brightness,
)
from b_logicx.models import BLXEvent


def _cfg(
    group: int = 5,
    address: int = 40,
    *,
    remembers_level: bool = False,
    participates_in_moods: bool = True,
) -> DimmerConfig:
    return DimmerConfig(
        group=group,
        address=address,
        remembers_level=remembers_level,
        participates_in_moods=participates_in_moods,
    )


def _bus(*configs: DimmerConfig) -> DimmerBus:
    bus = DimmerBus()
    for cfg in configs:
        bus.upsert(cfg)
    return bus


def _ev(command: str, group: int, address: int) -> BLXEvent:
    return BLXEvent(command, group, address, b"\x00\x00")


def _feed(bus: DimmerBus, frames: list[tuple[str, int, int]], now: float = 10.0):
    changed: list[tuple[int, int]] = []
    for i, (command, group, address) in enumerate(frames):
        changed = bus.apply(_ev(command, group, address), now + i * 0.01)
    return changed


def test_brightness_endpoints():
    assert brightness_to_percent(255) == 100
    assert brightness_to_percent(1) == 1
    assert brightness_to_percent(0) == 0
    assert percent_to_brightness(100) == 255
    assert percent_to_brightness(1) >= 1
    assert percent_to_brightness(0) == 0


def test_data_timer_sets_level():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    assert bus.view(5, 40) == DimmerView(True, 40)


def test_percent_zero_is_on_at_zero():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 0), ("Timer", 5, 40)])
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent == 0


def test_data_above_100_and_other_group_are_ignored():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    _feed(bus, [("Data", 0, 101), ("Timer", 5, 40)], now=20.0)
    assert bus.view(5, 40).percent == 40
    _feed(bus, [("Data", 1, 10), ("Timer", 5, 40)], now=30.0)
    assert bus.view(5, 40).percent == 40


def test_ldm_data_select_is_not_a_level():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 2), ("Select", 1, 23), ("Timer", 5, 40)])
    assert bus.view(5, 40).percent is None
    assert bus.view(5, 40).is_on is None


def test_stale_data_is_dropped():
    bus = _bus(_cfg())
    bus.apply(_ev("Data", 0, 40), 10.0)
    bus.apply(_ev("Timer", 5, 40), 10.0 + 2.01)
    assert bus.view(5, 40).percent is None


def test_data_within_two_seconds_still_applies():
    bus = _bus(_cfg())
    bus.apply(_ev("Data", 0, 40), 10.0)
    bus.apply(_ev("Timer", 5, 40), 12.0)
    assert bus.view(5, 40).percent == 40


def test_timer_without_data_leaves_the_level():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    _feed(bus, [("Timer", 5, 40)], now=20.0)
    assert bus.view(5, 40).percent == 40


def test_plain_set_is_full_on_when_not_remembering():
    bus = _bus(_cfg())
    _feed(bus, [("Set", 5, 40)])
    assert bus.view(5, 40) == DimmerView(True, 100)


def test_remember_restores_level_after_off_on():
    bus = _bus(_cfg(remembers_level=True))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Reset", 5, 40)])
    assert bus.view(5, 40).is_on is False
    assert bus.view(5, 40).percent is None
    _feed(bus, [("Set", 5, 40)], now=20.0)
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent == 40


def test_remember_off_drops_the_level():
    bus = _bus(_cfg(remembers_level=False))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Reset", 5, 40), ("Set", 5, 40)])
    assert bus.view(5, 40).percent == 100


def test_set_while_on_keeps_the_known_level():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Set", 5, 40)])
    assert bus.view(5, 40).percent == 40


def test_sfeer_clears_percent_and_set_stays_unknown():
    bus = _bus(_cfg(remembers_level=True))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 221)])
    assert bus.view(5, 40).percent is None
    assert bus.view(5, 40).is_on is True
    _feed(bus, [("Set", 5, 40)], now=20.0)
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None


def test_sfeer_reset_answers_off():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 228), ("Reset", 5, 40)])
    assert bus.view(5, 40).is_on is False
    assert bus.view(5, 40).percent is None


def test_sfeer_between_off_and_on_drops_remembered_level():
    bus = _bus(_cfg(remembers_level=True))
    _feed(
        bus,
        [
            ("Data", 0, 40),
            ("Timer", 5, 40),
            ("Reset", 5, 40),
            ("Dimmer", 5, 221),
            ("Set", 5, 40),
        ],
    )
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None


def test_sfeer_only_affects_participating_dimmers_in_that_group():
    bus = _bus(
        _cfg(address=40),
        _cfg(address=41, participates_in_moods=False),
        _cfg(group=6, address=40),
    )
    _feed(
        bus,
        [
            ("Data", 0, 40),
            ("Timer", 5, 40),
            ("Data", 0, 55),
            ("Timer", 5, 41),
            ("Data", 0, 70),
            ("Timer", 6, 40),
            ("Dimmer", 5, 221),
        ],
    )
    assert bus.view(5, 40).percent is None
    assert bus.view(5, 41).percent == 55
    assert bus.view(6, 40).percent == 70


def test_addresses_outside_221_228_are_not_a_sfeer():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 220)])
    assert bus.view(5, 40).percent == 40
    _feed(bus, [("Dimmer", 5, 229)], now=20.0)
    assert bus.view(5, 40).percent == 40


def test_press_and_hold_clears_only_the_percent():
    bus = _bus(_cfg(remembers_level=True))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 40)])
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent == 40
    assert bus.commit_hold((5, 40), 11.0)
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None
    _feed(bus, [("Reset", 5, 40), ("Set", 5, 40)], now=20.0)
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None


def test_close_dimmer_pair_keeps_the_percent():
    bus = _bus(_cfg(remembers_level=True))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 40), ("Dimmer", 5, 220)])
    assert bus.view(5, 40) == DimmerView(True, 40)
    assert bus.hold_delay((5, 40), 10.05) is None
    assert dimmer_toggle_frames(5, 40) == [
        ("Dimmer", 5, 40),
        ("Dimmer", 5, DIMMER_STOP_ADDRESS),
    ]


def test_late_stop_clears_the_percent_and_does_not_restore_it():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    bus.apply(_ev("Dimmer", 5, 40), 10.0)
    bus.apply(_ev("Dimmer", 5, 220), 10.0 + DIMMER_TAP_WINDOW_S + 0.05)
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None
    bus.apply(_ev("Dimmer", 5, 220), 12.0)
    assert bus.view(5, 40).percent is None


def test_stop_alone_leaves_the_percent():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40), ("Dimmer", 5, 220)])
    assert bus.view(5, 40).percent == 40


def test_own_toggle_echo_does_not_clear_the_percent():
    bus = _bus(_cfg())
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    bus.note_own_toggle(5, 40, 10.0)
    bus.apply(_ev("Dimmer", 5, 40), 10.02)
    bus.apply(_ev("Dimmer", 5, 220), 10.03)
    assert bus.take_new_holds() == []
    assert bus.commit_hold((5, 40), 10.0 + DIMMER_TAP_WINDOW_S + 0.05) is False
    assert bus.view(5, 40).percent == 40


def test_stop_closes_every_fresh_start_in_the_group():
    bus = _bus(_cfg(address=40), _cfg(address=41), _cfg(group=6, address=40))
    _feed(bus, [("Data", 0, 40), ("Timer", 5, 40)])
    _feed(bus, [("Data", 0, 55), ("Timer", 5, 41)], now=11.0)
    _feed(bus, [("Data", 0, 70), ("Timer", 6, 40)], now=12.0)
    bus.apply(_ev("Dimmer", 5, 40), 13.0)
    bus.apply(_ev("Dimmer", 5, 41), 13.01)
    bus.apply(_ev("Dimmer", 6, 40), 13.01)
    bus.apply(_ev("Dimmer", 5, 220), 13.02)
    assert bus.view(5, 40).percent == 40
    assert bus.view(5, 41).percent == 55
    assert bus.hold_delay((6, 40), 13.02) is not None
    assert bus.commit_hold((6, 40), 13.02 + DIMMER_TAP_WINDOW_S + 0.02)
    assert bus.view(6, 40).percent is None


def test_second_set_after_sfeer_does_not_invent_a_level():
    bus = _bus(_cfg())
    _feed(bus, [("Dimmer", 5, 222), ("Set", 5, 40), ("Set", 5, 40)])
    assert bus.view(5, 40).is_on is True
    assert bus.view(5, 40).percent is None


def test_status_set_is_put_back_to_the_saved_percent():
    """Status answers Set, which shows 100% without Memo. The saved level stays."""
    bus = _bus(_cfg())
    _feed(bus, [("Set", 5, 40)])
    assert bus.view(5, 40) == DimmerView(True, 100)
    bus.seed(5, 40, True, 40)
    assert bus.view(5, 40) == DimmerView(True, 40)

    memo = _bus(_cfg(remembers_level=True))
    _feed(memo, [("Set", 5, 40)])
    assert memo.view(5, 40) == DimmerView(True, None)
    memo.seed(5, 40, True, 35)
    assert memo.view(5, 40) == DimmerView(True, 35)

    _feed(memo, [("Reset", 5, 40)])
    memo.seed(5, 40, False, 35)
    assert memo.view(5, 40) == DimmerView(False, None)
    _feed(memo, [("Set", 5, 40)])
    assert memo.view(5, 40) == DimmerView(True, 35)


def test_seed_on_shows_the_percent():
    bus = _bus(_cfg())
    bus.seed(5, 40, True, 40)
    assert bus.view(5, 40) == DimmerView(True, 40)


def test_seed_off_with_memo_comes_back_on_set():
    bus = _bus(_cfg(remembers_level=True))
    bus.seed(5, 40, False, 35)
    assert bus.view(5, 40) == DimmerView(False, None)
    _feed(bus, [("Set", 5, 40)])
    assert bus.view(5, 40) == DimmerView(True, 35)


def test_seed_off_without_memo_sets_full_on_set():
    bus = _bus(_cfg())
    bus.seed(5, 40, False, 35)
    _feed(bus, [("Set", 5, 40)])
    assert bus.view(5, 40) == DimmerView(True, 100)


def test_seed_on_without_a_percent_stays_unknown():
    bus = _bus(_cfg(remembers_level=True))
    bus.seed(5, 40, True, None)
    assert bus.view(5, 40) == DimmerView(True, None)


def test_seed_unknown_or_missing_slot_is_left_alone():
    bus = _bus(_cfg())
    bus.seed(5, 40, None, 40)
    assert bus.view(5, 40) == DimmerView(None, None)
    empty = DimmerBus()
    empty.seed(5, 40, True, 40)
    assert empty.view(5, 40) == DimmerView(None, None)
