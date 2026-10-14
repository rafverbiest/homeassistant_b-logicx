"""AUD command pairing (pure, no HA).

A command is Misc 0.N followed immediately by Select <group>.<address>.
Other datagrams in between do not cancel the pending Misc
A newer Misc replaces the pending one, so two different media player
commands might collide, but we did not invent the protocol.
Select for a non-AUD address does not consume the pending Misc.
"""

from __future__ import annotations

from dataclasses import dataclass

AUD_MISC_GROUP = 0
AUD_MAX_AGE_S = 2.0
# How long an echoed mirror command stays marked, same window as a SoftM reply.
AUD_OWN_ECHO_S = 0.15

# Misc 0.N — the address byte is the action. Volume up is 9, volume down is 10.
AUD_STOP = 0
AUD_SOURCE_MIN = 1
AUD_SOURCE_MAX = 8
AUD_VOLUME_UP = 9
AUD_VOLUME_DOWN = 10
AUD_PLAY = 11
AUD_MUTE_ON = 12
AUD_MUTE_OFF = 13

AUD_COMMANDS = frozenset(range(0, 14))


@dataclass
class AudCommand:
    """A Misc that was committed by Select. group and address are the player.

    code is the Misc address byte (stop, source 1–8, volume, play, mute).
    """

    group: int
    address: int
    code: int


@dataclass
class AudPlayerState:
    """Last known player condition. There is no Status reply to refresh it."""

    state: str | None = None  # "playing" or "idle"
    source_index: int | None = None  # 1..8
    muted: bool = False


@dataclass(frozen=True, slots=True)
class AudTargetCall:
    """One call to make on the linked Home Assistant player."""

    service: str
    source: str | None = None
    mute: bool | None = None
    volume_level: float | None = None


@dataclass(frozen=True, slots=True)
class LinkedResult:
    """The call for one press, and the volume to keep for a later unmute.

    prelude is sent first and awaited. Play uses it for turn_on.
    """

    call: AudTargetCall | None
    saved_volume: float | None
    prelude: AudTargetCall | None = None


# Home Assistant MediaPlayerEntityFeature bits. Checked once, while configuring.
FEATURE_PAUSE = 1
FEATURE_VOLUME_SET = 4
FEATURE_VOLUME_MUTE = 8
FEATURE_TURN_ON = 128
FEATURE_TURN_OFF = 256
FEATURE_VOLUME_STEP = 1024
FEATURE_STOP = 4096

_FEATURE_NAMES = {
    "pause": FEATURE_PAUSE,
    "volume_set": FEATURE_VOLUME_SET,
    "volume_mute": FEATURE_VOLUME_MUTE,
    "turn_on": FEATURE_TURN_ON,
    "turn_off": FEATURE_TURN_OFF,
    "volume_step": FEATURE_VOLUME_STEP,
    "stop": FEATURE_STOP,
}

# States where turn_on runs before play. Idle and playing are left alone.
POWER_OFF_STATES = frozenset({"off", "standby"})

# Linked-player states that mirror onto the bus as play or stop.
MIRROR_PLAYING = frozenset({"playing", "buffering"})
MIRROR_IDLE = frozenset({"idle", "paused", "off", "standby"})

STOP_ACTION_STOP = "stop"
STOP_ACTION_PAUSE = "pause"
STOP_ACTION_TURN_OFF = "turn_off"
STOP_ACTIONS = (STOP_ACTION_STOP, STOP_ACTION_PAUSE, STOP_ACTION_TURN_OFF)

MUTE_ACTION_MUTE = "mute"
MUTE_ACTION_VOLUME = "volume"
MUTE_ACTIONS = (MUTE_ACTION_MUTE, MUTE_ACTION_VOLUME)

DEFAULT_VOLUME_STEP = 5
VOLUME_STEP_MIN = 1
VOLUME_STEP_MAX = 20
# Mute off after a restart, when the previous level was not kept.
UNMUTE_LEVEL = 0.2


def supported_feature_mask(raw: object) -> int:
    """The feature bits from a media player's supported_features attribute."""
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, (list, tuple, set)):
        mask = 0
        for item in raw:
            if isinstance(item, int) and not isinstance(item, bool):
                mask |= item
            else:
                mask |= _FEATURE_NAMES.get(str(item).strip().lower(), 0)
        return mask
    return 0


def stop_choices(features: int) -> list[str]:
    """Stop commands this player offers, preferred one first."""
    choices: list[str] = []
    if features & FEATURE_STOP:
        choices.append(STOP_ACTION_STOP)
    if features & FEATURE_PAUSE:
        choices.append(STOP_ACTION_PAUSE)
    if features & FEATURE_TURN_OFF:
        choices.append(STOP_ACTION_TURN_OFF)
    return choices


def mute_choices(features: int) -> list[str]:
    """Mute commands this player offers, preferred one first."""
    choices: list[str] = []
    if features & FEATURE_VOLUME_MUTE:
        choices.append(MUTE_ACTION_MUTE)
    if features & FEATURE_VOLUME_SET:
        choices.append(MUTE_ACTION_VOLUME)
    return choices


def can_set_volume(features: int) -> bool:
    return bool(features & FEATURE_VOLUME_SET)


def can_turn_on(features: int) -> bool:
    return bool(features & FEATURE_TURN_ON)


def keep_or_default(saved: object, choices: list[str]) -> str | None:
    """The saved choice when this player still offers it, otherwise the first."""
    text = str(saved or "").strip().lower()
    if text in choices:
        return text
    if choices:
        return choices[0]
    return None


def stepped_volume(level: float | None, step_points: int, *, up: bool) -> float | None:
    """Current level plus or minus step_points, as a fraction from 0 to 1.

    None when the player is not reporting a level.
    """
    if level is None:
        return None
    current = round(float(level) * 100)
    nxt = current + step_points if up else current - step_points
    if nxt < 0:
        nxt = 0
    elif nxt > 100:
        nxt = 100
    return nxt / 100


def linked_call(
    code: int,
    sources: list[str],
    *,
    stop_action: str | None = None,
    mute_action: str | None = None,
    volume_step: int | None = None,
    volume_level: float | None = None,
    saved_volume: float | None = None,
    turn_on_with_play: bool = False,
    player_state: str | None = None,
) -> LinkedResult:
    """The stored command for one Misc code.

    saved_volume is the level kept by mute-to-zero. The result carries the
    value to keep after this press. A missing call means the press does
    nothing to the linked player.
    """
    saved = saved_volume
    if code == AUD_STOP:
        service = {
            STOP_ACTION_STOP: "media_stop",
            STOP_ACTION_PAUSE: "media_pause",
            STOP_ACTION_TURN_OFF: "turn_off",
        }.get(str(stop_action or ""))
        if service is None:
            return LinkedResult(None, saved)
        return LinkedResult(AudTargetCall(service), saved)
    if code == AUD_PLAY:
        prelude = None
        if turn_on_with_play and str(player_state or "") in POWER_OFF_STATES:
            prelude = AudTargetCall("turn_on")
        return LinkedResult(AudTargetCall("media_play"), saved, prelude)
    if code in (AUD_VOLUME_UP, AUD_VOLUME_DOWN):
        if volume_step is not None:
            nxt = stepped_volume(
                volume_level, int(volume_step), up=code == AUD_VOLUME_UP
            )
            if nxt is not None:
                return LinkedResult(
                    AudTargetCall("volume_set", volume_level=nxt), saved
                )
        service = "volume_up" if code == AUD_VOLUME_UP else "volume_down"
        return LinkedResult(AudTargetCall(service), saved)
    if code == AUD_MUTE_ON:
        if mute_action == MUTE_ACTION_MUTE:
            return LinkedResult(AudTargetCall("volume_mute", mute=True), saved)
        if mute_action == MUTE_ACTION_VOLUME:
            if volume_level is not None and volume_level > 0:
                saved = float(volume_level)
            return LinkedResult(AudTargetCall("volume_set", volume_level=0.0), saved)
        return LinkedResult(None, saved)
    if code == AUD_MUTE_OFF:
        if mute_action == MUTE_ACTION_MUTE:
            return LinkedResult(AudTargetCall("volume_mute", mute=False), saved)
        if mute_action == MUTE_ACTION_VOLUME:
            level = saved if saved is not None and saved > 0 else UNMUTE_LEVEL
            return LinkedResult(AudTargetCall("volume_set", volume_level=level), saved)
        return LinkedResult(None, saved)
    if AUD_SOURCE_MIN <= code <= AUD_SOURCE_MAX:
        index = code - 1
        if index >= len(sources):
            return LinkedResult(None, saved)
        return LinkedResult(
            AudTargetCall("select_source", source=sources[index]), saved
        )
    return LinkedResult(None, saved)


def target_call(code: int, sources: list[str]) -> AudTargetCall | None:
    """The linked-player call for one Misc code. None when the code is unused.

    Stop and mute here assume a player that has those features. The options
    screen stores the real choice, and linked_call performs that.
    """
    return linked_call(
        code,
        sources,
        stop_action=STOP_ACTION_STOP,
        mute_action=MUTE_ACTION_MUTE,
    ).call


def mirror_codes(
    player: AudPlayerState,
    *,
    state: str | None,
    source: str | None,
    sources: list[str],
    muted: bool | None,
) -> list[int]:
    """Codes to send so the displays follow the linked player.

    A source outside the eight names is ignored, and so is volume. A source
    code already means that source is playing, so play is not sent beside it.
    Play, stop, and mute are sent when they change on their own.
    """
    codes: list[int] = []
    reported = str(source or "").strip()
    foreign = bool(reported) and reported not in sources
    if not foreign:
        source_sent = False
        if reported:
            code = sources.index(reported) + 1
            if player.source_index != code:
                codes.append(code)
                source_sent = True
        if not source_sent:
            if state in MIRROR_PLAYING and player.state != "playing":
                codes.append(AUD_PLAY)
            elif state in MIRROR_IDLE and player.state == "playing":
                codes.append(AUD_STOP)
    if muted is not None and muted != player.muted:
        codes.append(AUD_MUTE_ON if muted else AUD_MUTE_OFF)
    return codes


def _unique_labels(items: list[str]) -> list[str]:
    names: list[str] = []
    for item in items:
        label = str(item).strip()
        if label and label not in names:
            names.append(label)
    return names


def aud_link_options(
    reported: list[str],
    saved: list[str],
    *,
    same_player: bool,
) -> list[str] | None:
    """Options for the eight source dropdowns.

    Sources the player is reporting now are the whole list. Names already
    stored stay available only for that same player when it is reporting
    nothing, so the edit screen can still open. None means there is nothing
    to offer.
    """
    live = _unique_labels(reported)
    if live:
        return live
    if same_player:
        kept = _unique_labels(saved)
        if kept:
            return kept
    return None


def apply_aud_command(player: AudPlayerState, code: int) -> None:
    """Update the remembered player from one Misc code.

    Stop leaves the source name in place and sets idle. Play does not change
    the source. Volume up and down change nothing here: the bus has no level
    to store. Mute is remembered on its own.
    """
    if code == AUD_STOP:
        player.state = "idle"
    elif AUD_SOURCE_MIN <= code <= AUD_SOURCE_MAX:
        player.state = "playing"
        player.source_index = code
    elif code == AUD_PLAY:
        player.state = "playing"
    elif code == AUD_MUTE_ON:
        player.muted = True
    elif code == AUD_MUTE_OFF:
        player.muted = False


class AudBusState:
    """One sticky Misc slot for every AUD on the bus."""

    def __init__(self) -> None:
        self._code: int | None = None
        self._at: float = 0.0

    def note(
        self,
        command: str,
        group: int,
        address: int,
        now: float,
        *,
        aud_keys: set[tuple[int, int]],
    ) -> AudCommand | None:
        """Watch the bus for Misc 0.N, then Select of a configured player.

        Returns the command only when that Select arrives within 2 seconds.
        Anything else, including Select for a light sensor, leaves the pending
        Misc where it is. A newer Misc replaces it. There is one slot for
        every player, so two modules inside 2 seconds share it and the later
        Misc wins.
        """
        g = int(group) & 0x0F
        a = int(address) & 0xFF
        if command == "Misc" and g == AUD_MISC_GROUP and a in AUD_COMMANDS:
            self._code = a
            self._at = now
            return None
        if command != "Select":
            return None
        if (g, a) not in aud_keys:
            return None
        if self._code is None or (now - self._at) > AUD_MAX_AGE_S:
            self._code = None
            return None
        code = self._code
        self._code = None
        return AudCommand(group=g, address=a, code=code)
