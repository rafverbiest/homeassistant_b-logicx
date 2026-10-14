"""AUD Misc/Select pairing and player-state effects (no Home Assistant)."""

from __future__ import annotations

from b_logicx.audio import (
    AUD_MAX_AGE_S,
    AUD_MUTE_OFF,
    AUD_MUTE_ON,
    AUD_OWN_ECHO_S,
    AUD_PLAY,
    AUD_STOP,
    AUD_VOLUME_DOWN,
    AUD_VOLUME_UP,
    AudBusState,
    AudPlayerState,
    apply_aud_command,
    FEATURE_PAUSE,
    FEATURE_STOP,
    FEATURE_TURN_OFF,
    FEATURE_VOLUME_MUTE,
    FEATURE_VOLUME_SET,
    aud_link_options,
    keep_or_default,
    linked_call,
    mirror_codes,
    mute_choices,
    stepped_volume,
    stop_choices,
    supported_feature_mask,
    target_call,
)

AUD = {(4, 1), (4, 2)}


def test_volume_misc_codes():
    # Wire codes: Misc 0.9 is volume up, Misc 0.10 is volume down.
    assert AUD_VOLUME_UP == 9
    assert AUD_VOLUME_DOWN == 10


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


def test_target_call_maps_each_bus_code():
    sources = [f"S{i}" for i in range(1, 9)]
    assert target_call(AUD_STOP, sources).service == "media_stop"
    assert target_call(AUD_PLAY, sources).service == "media_play"
    assert target_call(AUD_VOLUME_UP, sources).service == "volume_up"
    assert target_call(AUD_VOLUME_DOWN, sources).service == "volume_down"
    muted = target_call(AUD_MUTE_ON, sources)
    assert muted.service == "volume_mute" and muted.mute is True
    assert target_call(AUD_MUTE_OFF, sources).mute is False
    picked = target_call(3, sources)
    assert picked.service == "select_source" and picked.source == "S3"
    assert target_call(3, ["Only"]) is None
    assert target_call(14, sources) is None


def test_player_features_choose_stop_and_mute():
    pause_and_volume = FEATURE_PAUSE | FEATURE_VOLUME_SET
    assert stop_choices(pause_and_volume) == ["pause"]
    assert mute_choices(pause_and_volume) == ["volume"]
    both = FEATURE_STOP | FEATURE_PAUSE | FEATURE_VOLUME_MUTE | FEATURE_VOLUME_SET
    assert stop_choices(both) == ["stop", "pause"]
    assert mute_choices(both) == ["mute", "volume"]
    assert stop_choices(FEATURE_TURN_OFF) == ["turn_off"]
    assert stop_choices(0) == []
    assert keep_or_default("pause", ["stop", "pause"]) == "pause"
    assert keep_or_default("stop", ["pause"]) == "pause"
    assert keep_or_default("", []) is None
    assert supported_feature_mask(["pause", "volume_set"]) == pause_and_volume
    assert supported_feature_mask(True) == 0


def test_linked_call_uses_the_stored_commands():
    sources = ["Radio", "CD"]
    paused = linked_call(AUD_STOP, sources, stop_action="pause")
    assert paused.call.service == "media_pause"
    assert linked_call(AUD_STOP, sources, stop_action="turn_off").call.service == (
        "turn_off"
    )
    assert linked_call(AUD_STOP, sources).call is None
    muted = linked_call(
        AUD_MUTE_ON,
        sources,
        mute_action="volume",
        volume_level=0.22,
    )
    assert muted.call.service == "volume_set"
    assert muted.call.volume_level == 0.0
    assert muted.saved_volume == 0.22
    restored = linked_call(
        AUD_MUTE_OFF,
        sources,
        mute_action="volume",
        saved_volume=muted.saved_volume,
    )
    assert restored.call.volume_level == 0.22
    after_restart = linked_call(AUD_MUTE_OFF, sources, mute_action="volume")
    assert after_restart.call.volume_level == 0.2
    assert linked_call(AUD_MUTE_ON, sources).call is None
    step = linked_call(
        AUD_VOLUME_UP,
        sources,
        volume_step=5,
        volume_level=0.22,
    )
    assert step.call.service == "volume_set" and step.call.volume_level == 0.27
    assert stepped_volume(0.03, 5, up=False) == 0.0
    assert stepped_volume(0.96, 5, up=True) == 1.0
    assert stepped_volume(None, 5, up=True) is None
    missing_level = linked_call(AUD_VOLUME_DOWN, sources, volume_step=5)
    assert missing_level.call.service == "volume_down"
    assert linked_call(3, sources).call is None
    waking = linked_call(
        AUD_PLAY, sources, turn_on_with_play=True, player_state="off"
    )
    assert waking.prelude.service == "turn_on"
    assert waking.call.service == "media_play"
    standby = linked_call(
        AUD_PLAY, sources, turn_on_with_play=True, player_state="standby"
    )
    assert standby.prelude.service == "turn_on"
    already = linked_call(
        AUD_PLAY, sources, turn_on_with_play=True, player_state="idle"
    )
    assert already.prelude is None and already.call.service == "media_play"
    assert (
        linked_call(AUD_PLAY, sources, player_state="off").prelude is None
    )


def test_mirror_codes_follow_source_play_stop_and_mute():
    # The mark window matches a SoftM own-echo. Volume has no code here.
    assert AUD_OWN_ECHO_S == 0.15
    sources = ["Radio", "CD", "Radio"]
    blank = AudPlayerState()

    # A source change is that code alone, even while the player is playing.
    # A repeated name uses the first slot.
    assert mirror_codes(
        blank, state="playing", source="Radio", sources=sources, muted=False
    ) == [1]
    assert mirror_codes(
        blank, state="playing", source="  CD  ", sources=sources, muted=False
    ) == [2]
    # Paused plus a new source still sends only the source code.
    assert mirror_codes(
        blank, state="paused", source="CD", sources=sources, muted=False
    ) == [2]

    playing = AudPlayerState(state="playing", source_index=2)
    assert mirror_codes(
        playing, state="playing", source="CD", sources=sources, muted=False
    ) == []
    idle = AudPlayerState(state="idle", source_index=2)
    assert mirror_codes(
        idle, state="playing", source="CD", sources=sources, muted=False
    ) == [AUD_PLAY]
    assert mirror_codes(
        idle, state="buffering", source="CD", sources=sources, muted=None
    ) == [AUD_PLAY]
    # No source name still counts as play, not as a foreign source.
    assert mirror_codes(
        AudPlayerState(state="idle"),
        state="playing",
        source="",
        sources=sources,
        muted=None,
    ) == [AUD_PLAY]
    assert mirror_codes(
        AudPlayerState(state="idle"),
        state="playing",
        source=None,
        sources=sources,
        muted=None,
    ) == [AUD_PLAY]

    for reported in ("paused", "idle", "off", "standby"):
        assert mirror_codes(
            playing, state=reported, source="CD", sources=sources, muted=False
        ) == [AUD_STOP]
    # Already idle, or a state the bus cannot show, sends nothing.
    assert mirror_codes(
        idle, state="paused", source="CD", sources=sources, muted=False
    ) == []
    for reported in ("on", "unavailable", "unknown"):
        assert mirror_codes(
            playing, state=reported, source="CD", sources=sources, muted=False
        ) == []

    # Outside the eight names: no source, play, or stop. Mute still can.
    assert mirror_codes(
        playing, state="paused", source="Bluetooth", sources=sources, muted=False
    ) == []
    assert mirror_codes(
        playing, state="playing", source="Bluetooth", sources=sources, muted=True
    ) == [AUD_MUTE_ON]
    assert mirror_codes(
        blank, state="playing", source="CD", sources=sources, muted=True
    ) == [2, AUD_MUTE_ON]
    muted = AudPlayerState(state="playing", source_index=2, muted=True)
    assert mirror_codes(
        muted, state="playing", source="CD", sources=sources, muted=False
    ) == [AUD_MUTE_OFF]
    assert mirror_codes(
        muted, state="playing", source="CD", sources=sources, muted=None
    ) == []
    assert mirror_codes(
        muted, state="playing", source="CD", sources=sources, muted=True
    ) == []


def test_aud_link_options_prefer_what_the_player_reports():
    reported = ["Radio", " Radio ", "CD", ""]
    saved = ["Old radio", "CD"]
    assert aud_link_options(reported, saved, same_player=True) == ["Radio", "CD"]
    assert aud_link_options([], saved, same_player=True) == ["Old radio", "CD"]
    assert aud_link_options([], saved, same_player=False) is None
    assert aud_link_options(["  "], ["", "  "], same_player=True) is None
