"""BL-AUD command pairing (pure, no HA).

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
