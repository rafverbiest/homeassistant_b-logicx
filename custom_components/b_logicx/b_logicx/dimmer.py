"""Track one dimmer's on/off and percent from the bus.

A level is two frames, the same pair BLConfig sends: Data 0.<percent>,
then Timer on the dimmer's own group and address. Percent is 0–100.

Set turns that dimmer on. Reset turns it off.

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


class DimmerBus:
    """Pending Data percent, and one slot per configured dimmer."""

    def __init__(self) -> None:
        self._slots: dict[tuple[int, int], _Slot] = {}
        self._pending: int | None = None
        self._pending_at: float | None = None

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
            self._note_dimmer(group, address)
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

    def _note_dimmer(self, group: int, address: int) -> None:
        if SFEER_ADDRESS_MIN <= address <= SFEER_ADDRESS_MAX:
            for slot in self._slots.values():
                if slot.config.group != group:
                    continue
                if not slot.config.participates_in_moods:
                    continue
                slot.percent = None
                slot.memory = None
                slot.mood_pending = True
            return
        slot = self._slots.get((group, address))
        if slot is None:
            return
        # Press-and-hold on this dimmer. The level moved. On/off did not.
        slot.percent = None
        slot.memory = None

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
