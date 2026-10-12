"""Track one dimmer's on/off and percent from the bus.

A level is two frames, the same pair BLConfig sends: Data 0.<percent>,
then Timer on the dimmer's own group and address. Percent is 0–100.

Set turns that dimmer on. Reset turns it off. Those frames come from the
module. This integration does not send them to switch the lamp.

A tap is Dimmer on the dimmer's own address, then Dimmer <group>.220, with
barely any time between them. 220 means stop dimming. Together they act like
Toggle and the known percent stays. Dimmer on the dimmer's own address with
no stop inside that short window is a hold: the level moved, so the percent
is cleared. A later stop does not bring it back.

A Sfeer is Dimmer to an address from 221 through 228 in the dimmer's group.
The dimmer module answers on its own address with Set or Reset. That answer
says whether the lamp is on. It does not say the recorded percent.

remembers_level describes the module. When it is on, the module keeps its
level across off and on, and this tracker keeps the same number so a slider
can show it again. When it is off, a plain Set turns the lamp on at 100%.

A Set or Reset that answers a Sfeer does not use that memory and does not
show 100%. The recorded level is not read back.

Data 0.2 followed by Select is an LDM request. Select drops a pending percent
so that pair is not later applied as 2%.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import BLXEvent

# Filed Sfeer addresses. Eight moods per room, in the room's group.
SFEER_ADDRESS_MIN = 221
SFEER_ADDRESS_MAX = 228

# Dimmer <group>.220 stops dimming. Start plus this stop inside the window
# is a tap. Start left alone past the window is a hold.
DIMMER_STOP_ADDRESS = 220
DIMMER_TAP_WINDOW_S = 0.15

# Data 0.<percent>: group 0, address byte is the percent.
DIMMER_DATA_GROUP = 0
DIMMER_PERCENT_MAX = 100

# Same give-up window as the other sticky slots.
DIMMER_PENDING_MAX_AGE_S = 2.0

# A module that does not remember its level turns on at full.
ON_LEVEL_WITHOUT_MEMORY = 100


@dataclass(frozen=True, slots=True)
class DimmerConfig:
    """How one physical dimmer was programmed. Not written back to the module."""

    group: int
    address: int
    remembers_level: bool = False
    participates_in_moods: bool = True

    @property
    def key(self) -> tuple[int, int]:
        return (int(self.group) & 0x0F, int(self.address) & 0xFF)


@dataclass(frozen=True, slots=True)
class DimmerView:
    """What to show. percent is None when the level is not known."""

    is_on: bool | None
    percent: int | None


@dataclass
class _Slot:
    config: DimmerConfig
    is_on: bool | None = None
    percent: int | None = None
    memory: int | None = None
    mood_pending: bool = False


def percent_to_brightness(percent: int) -> int:
    """Map 0–100 onto Home Assistant brightness 0–255. 100 stays 255."""
    p = max(0, min(DIMMER_PERCENT_MAX, int(percent)))
    if p <= 0:
        return 0
    return min(255, max(1, round(p * 255 / 100)))


def brightness_to_percent(brightness: int) -> int:
    """Map Home Assistant brightness 0–255 onto 0–100. 255 stays 100."""
    b = max(0, min(255, int(brightness)))
    if b <= 0:
        return 0
    return min(DIMMER_PERCENT_MAX, max(1, round(b * 100 / 255)))


def dimmer_toggle_frames(group: int, address: int) -> list[tuple[str, int, int]]:
    """One tap: start dimming this module, then stop."""
    g = int(group) & 0x0F
    a = int(address) & 0xFF
    return [("Dimmer", g, a), ("Dimmer", g, DIMMER_STOP_ADDRESS)]


class DimmerBus:
    """Pending Data percent, and one slot per configured dimmer."""

    def __init__(self) -> None:
        self._slots: dict[tuple[int, int], _Slot] = {}
        self._pending: int | None = None
        self._pending_at: float | None = None
        # Dimmer on a module's own address, waiting for stop or for the window.
        self._dim_started: dict[tuple[int, int], float] = {}
        # Taps this integration just sent. Their echo must not clear the percent.
        self._own_toggle: dict[tuple[int, int], float] = {}
        self._new_holds: list[tuple[int, int]] = []

    def upsert(self, config: DimmerConfig) -> None:
        """Add or replace one dimmer's flags. An existing level is kept."""
        old = self._slots.get(config.key)
        slot = _Slot(config=config)
        if old is not None:
            slot.is_on = old.is_on
            slot.percent = old.percent
            slot.memory = old.memory
            slot.mood_pending = old.mood_pending
        self._slots[config.key] = slot

    def view(self, group: int, address: int) -> DimmerView:
        """Current on/off and percent. Unknown when this dimmer is not configured."""
        slot = self._slots.get((int(group) & 0x0F, int(address) & 0xFF))
        if slot is None:
            return DimmerView(None, None)
        return DimmerView(slot.is_on, slot.percent)

    def apply(self, event: BLXEvent, now: float) -> list[tuple[int, int]]:
        """Fold one frame in. Return dimmers whose on/off or percent changed."""
        before = {key: (slot.is_on, slot.percent) for key, slot in self._slots.items()}
        self._apply(event, now)
        return [
            key
            for key, slot in self._slots.items()
            if (slot.is_on, slot.percent) != before.get(key)
        ]

    def _apply(self, event: BLXEvent, now: float) -> None:
        cmd = event.command
        group = int(event.group) & 0x0F
        address = int(event.address) & 0xFF

        if cmd == "Data":
            self._note_data(group, address, now)
            return
        if cmd == "Select":
            self._pending = None
            self._pending_at = None
            return
        if cmd == "Timer":
            self._note_timer(group, address, now)
            return
        if cmd == "Dimmer":
            self._note_dimmer(group, address, now)
            return
        if cmd == "Set":
            self._note_set(group, address)
            return
        if cmd == "Reset":
            self._note_reset(group, address)

    def _note_data(self, group: int, address: int, now: float) -> None:
        if group != DIMMER_DATA_GROUP:
            return
        if address > DIMMER_PERCENT_MAX:
            return
        self._pending = address
        self._pending_at = now

    def _note_timer(self, group: int, address: int, now: float) -> None:
        if self._pending is None or self._pending_at is None:
            return
        if now - self._pending_at > DIMMER_PENDING_MAX_AGE_S:
            self._pending = None
            self._pending_at = None
            return
        percent = self._pending
        self._pending = None
        self._pending_at = None
        slot = self._slots.get((group, address))
        if slot is None:
            return
        slot.percent = percent
        slot.memory = percent
        slot.is_on = True
        slot.mood_pending = False

    def note_own_toggle(self, group: int, address: int, now: float) -> None:
        """Remember a tap we are about to send, so its echo keeps the percent."""
        key = (int(group) & 0x0F, int(address) & 0xFF)
        self._own_toggle[key] = now

    def take_new_holds(self) -> list[tuple[int, int]]:
        """Starts recorded since the last call. The hub times these out."""
        new = self._new_holds
        self._new_holds = []
        return new

    def hold_delay(self, key: tuple[int, int], now: float) -> float | None:
        """Seconds until this start is past the tap window. None if it closed."""
        started = self._dim_started.get(key)
        if started is None:
            return None
        if now - started > DIMMER_TAP_WINDOW_S:
            return 0.0
        # Wake just past the boundary, so a stop at 150 ms still counts as a tap.
        return (started + DIMMER_TAP_WINDOW_S) - now + 0.001

    def commit_hold(self, key: tuple[int, int], now: float) -> bool:
        """Clear the percent when a start was left alone past the tap window.

        A start that is still inside the window stays pending. Returns whether
        the shown percent changed.
        """
        started = self._dim_started.get(key)
        if started is None:
            return False
        if now - started <= DIMMER_TAP_WINDOW_S:
            return False
        self._dim_started.pop(key, None)
        slot = self._slots.get(key)
        if slot is None:
            return False
        changed = slot.percent is not None
        self._forget_level(slot)
        return changed

    def _note_dimmer(self, group: int, address: int, now: float) -> None:
        if SFEER_ADDRESS_MIN <= address <= SFEER_ADDRESS_MAX:
            for key, slot in self._slots.items():
                if key[0] != group:
                    continue
                if not slot.config.participates_in_moods:
                    continue
                slot.percent = None
                slot.memory = None
                slot.mood_pending = True
                self._dim_started.pop(key, None)
            return
        if address == DIMMER_STOP_ADDRESS:
            self._close_starts(group, now)
            return
        self._begin_start(group, address, now)

    def _begin_start(self, group: int, address: int, now: float) -> None:
        key = (group, address)
        if key not in self._slots:
            return
        if self._own_toggle_covers(key, now):
            return
        self._dim_started[key] = now
        self._new_holds.append(key)

    def _close_starts(self, group: int, now: float) -> None:
        """Stop dimming in this group. A fresh start was a tap. An old one was a hold."""
        for key, started in list(self._dim_started.items()):
            if key[0] != group:
                continue
            self._dim_started.pop(key, None)
            if now - started <= DIMMER_TAP_WINDOW_S:
                continue
            slot = self._slots.get(key)
            if slot is not None:
                self._forget_level(slot)

    def _forget_level(self, slot: _Slot) -> None:
        slot.percent = None
        slot.memory = None

    def _own_toggle_covers(self, key: tuple[int, int], now: float) -> bool:
        started = self._own_toggle.get(key)
        if started is None:
            return False
        if now - started > DIMMER_TAP_WINDOW_S:
            self._own_toggle.pop(key, None)
            return False
        return True

    def _note_set(self, group: int, address: int) -> None:
        slot = self._slots.get((group, address))
        if slot is None:
            return
        if slot.mood_pending:
            slot.mood_pending = False
            slot.is_on = True
            slot.percent = None
            return
        if slot.is_on is True:
            return
        slot.is_on = True
        if slot.config.remembers_level and slot.memory is not None:
            slot.percent = slot.memory
            return
        if slot.config.remembers_level:
            slot.percent = None
            return
        slot.percent = ON_LEVEL_WITHOUT_MEMORY

    def _note_reset(self, group: int, address: int) -> None:
        slot = self._slots.get((group, address))
        if slot is None:
            return
        if slot.mood_pending:
            slot.mood_pending = False
            slot.is_on = False
            slot.percent = None
            return
        if slot.config.remembers_level and slot.percent is not None:
            slot.memory = slot.percent
        slot.is_on = False
        slot.percent = None
        if not slot.config.remembers_level:
            slot.memory = None
