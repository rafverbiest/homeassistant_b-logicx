"""BL-AUD Misc/Select pairing and player-state effects (no Home Assistant)."""

from __future__ import annotations

from b_logicx.audio import (
    AUD_MAX_AGE_S,
    AUD_MUTE_OFF,
    AUD_MUTE_ON,
    AUD_PLAY,
    AUD_STOP,
    AUD_VOLUME_DOWN,
    AUD_VOLUME_UP,
    AudBusState,
    AudPlayerState,
    apply_aud_command,
)

AUD = {(4, 1), (4, 2)}


def test_pair_survives_unrelated_frames():
    st = AudBusState()
    now = 100.0
    assert st.note("Misc", 0, AUD_PLAY, now, aud_keys=AUD) is None
    assert st.note("Set", 2, 33, now + 0.05, aud_keys=AUD) is None
    assert st.note("Value", 3, 49, now + 0.1, aud_keys=AUD) is None
    cmd = st.note("Select", 4, 1, now + 0.2, aud_keys=AUD)
    assert cmd is not None
    assert (cmd.group, cmd.address, cmd.code) == (4, 1, AUD_PLAY)


def test_select_for_other_device_does_not_consume_misc():
    st = AudBusState()
    now = 50.0
    st.note("Misc", 0, 3, now, aud_keys=AUD)
    # LDM-style Select for a light sensor must leave the pending Misc in place.
    assert st.note("Select", 1, 23, now + 0.1, aud_keys=AUD) is None
    cmd = st.note("Select", 4, 1, now + 0.2, aud_keys=AUD)
    assert cmd is not None and cmd.code == 3


def test_misc_expires_after_two_seconds():
    st = AudBusState()
    now = 10.0
    st.note("Misc", 0, AUD_STOP, now, aud_keys=AUD)
    assert st.note("Select", 4, 1, now + AUD_MAX_AGE_S, aud_keys=AUD) is not None

    st.note("Misc", 0, AUD_STOP, now, aud_keys=AUD)
    assert st.note("Select", 4, 1, now + AUD_MAX_AGE_S + 0.01, aud_keys=AUD) is None
    # Expired slot is cleared, so a later Select does not revive it.
    assert st.note("Select", 4, 1, now + 3.0, aud_keys=AUD) is None


def test_newer_misc_replaces_and_second_aud_wins():
    st = AudBusState()
    now = 0.0
    st.note("Misc", 0, 5, now, aud_keys=AUD)
    st.note("Misc", 0, 8, now + 0.05, aud_keys=AUD)
    cmd = st.note("Select", 4, 1, now + 0.1, aud_keys=AUD)
    assert cmd is not None and cmd.code == 8
    assert st.note("Select", 4, 2, now + 0.2, aud_keys=AUD) is None


def test_apply_play_stop_source_volume_mute():
    player = AudPlayerState()
    apply_aud_command(player, 2)
    assert player.state == "playing" and player.source_index == 2
    apply_aud_command(player, AUD_VOLUME_UP)
    apply_aud_command(player, AUD_VOLUME_DOWN)
    assert player.state == "playing" and player.source_index == 2
    apply_aud_command(player, AUD_MUTE_ON)
    assert player.muted is True and player.state == "playing"
    apply_aud_command(player, AUD_STOP)
    assert player.state == "idle" and player.source_index == 2 and player.muted is True
    apply_aud_command(player, AUD_PLAY)
    assert player.state == "playing" and player.source_index == 2
    apply_aud_command(player, AUD_MUTE_OFF)
    assert player.muted is False
