"""BL-AUD command pairing (pure, no HA).

A command is Misc 0.N followed, within 2 seconds, by Select <group>.<address>.
Other datagrams in between do not cancel the pending Misc (same idea as LDM/TSM).
A newer Misc replaces the pending one. Select for a non-AUD address does not
consume it.
"""

from __future__ import annotations

from dataclasses import dataclass

AUD_MISC_GROUP = 0
AUD_MAX_AGE_S = 2.0

# Misc address byte → action
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
    """Apply one Misc command code. Volume steps do not change play or mute."""
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
