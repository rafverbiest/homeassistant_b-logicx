"""Virtual SoftM status tracking (pure logic, no HA).

Mirrors a hardware Status Module (BL-STA) for Software Members:
  Toggle → flip + emit Set/Reset
  Status → reply Set/Reset from memory
  Set/Reset → update memory only
  Timer (optional) → Set, wait, Reset

  The Timer is not available in hardware BL-STA, rather it is called
  Software Member Timer, a part of B-INM based logic.

  The Software Member Timer implemented here is designed to be superior
  since it also obeys a Reset command (SoftM timers from INM's don't)

  Of course, here in Linux/Python we are also not bound by a maximum
  amount of SoftM's (as BL-STA is because of its hardware limitations)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SoftMConfig:
    """One tracked software member.

    default_state is used until something has set the memory. persist is stored
    for the Home Assistant switch; this tracker never reads it. timer_seconds
    None means a Timer command on this address is ignored.
    """

    group: int
    address: int
    timer_seconds: float | None = None  # None = no Timer handling
    persist: bool = True
    default_state: bool = False


@dataclass
class SoftMAction:
    """Outbound bus command(s) the hub should send."""

    command: str  # Set or Reset
    group: int
    address: int


@dataclass
class SoftMTracker:
    """In-memory SoftM bool map + timer bookkeeping keys."""

    # (g, a) -> is_on
    state: dict[tuple[int, int], bool] = field(default_factory=dict)
    configs: dict[tuple[int, int], SoftMConfig] = field(default_factory=dict)
    # Keys with an active timer (hub owns asyncio Tasks)
    active_timers: set[tuple[int, int]] = field(default_factory=set)

    def configure(self, entries: list[SoftMConfig]) -> None:
        """Install the tracked addresses. Existing on/off memory is kept."""
        self.configs = {(e.group, e.address): e for e in entries}
        for key, cfg in self.configs.items():
            if key not in self.state:
                self.state[key] = bool(cfg.default_state)

    def seed(self, group: int, address: int, is_on: bool) -> None:
        """Replace memory for a tracked address, for example after a restart."""
        key = (group, address)
        if key in self.configs:
            self.state[key] = is_on

    def is_tracked(self, group: int, address: int) -> bool:
        """True when this address was included in configure()."""
        return (group, address) in self.configs

    def get_state(self, group: int, address: int) -> bool | None:
        """Remembered on/off, or None if this address is not tracked."""
        key = (group, address)
        if key not in self.configs:
            return None
        return self.state.get(key, self.configs[key].default_state)

    def on_set_reset(self, group: int, address: int, is_on: bool) -> None:
        """Store Set as on and Reset as off. Does not start or cancel a timer."""
        key = (group, address)
        if key not in self.configs:
            return
        self.state[key] = is_on

    def on_toggle(self, group: int, address: int) -> SoftMAction | None:
        """Flip memory and return the Set or Reset that announces the new state.

        The timer key is dropped so a later expiry does nothing. The caller
        still has to cancel the waiting task.
        """
        key = (group, address)
        if key not in self.configs:
            return None
        self.active_timers.discard(key)
        cur = self.state.get(key, self.configs[key].default_state)
        new = not cur
        self.state[key] = new
        return SoftMAction("Set" if new else "Reset", group, address)

    def on_status(self, group: int, address: int) -> SoftMAction | None:
        """Reply Set or Reset from memory. A running timer is left running."""
        key = (group, address)
        if key not in self.configs:
            return None
        is_on = self.state.get(key, self.configs[key].default_state)
        return SoftMAction("Set" if is_on else "Reset", group, address)

    def on_timer(self, group: int, address: int) -> tuple[SoftMAction, float] | None:
        """Turn memory on and return (Set, seconds). None if this address has no timer.

        Marking the key active is how expiry later knows it was not cancelled.
        """
        key = (group, address)
        cfg = self.configs.get(key)
        if cfg is None or cfg.timer_seconds is None:
            return None
        secs = float(cfg.timer_seconds)
        if secs <= 0:
            return None
        self.state[key] = True
        self.active_timers.add(key)
        return SoftMAction("Set", group, address), secs

    def timer_expired(self, group: int, address: int) -> SoftMAction | None:
        """Turn memory off and return Reset, or None if the timer was cancelled."""
        key = (group, address)
        if key not in self.configs:
            return None
        if key not in self.active_timers:
            return None  # cancelled
        self.active_timers.discard(key)
        self.state[key] = False
        return SoftMAction("Reset", group, address)

    def cancel_timer(self, group: int, address: int) -> None:
        """Forget a running timer so expiry will not send Reset."""
        self.active_timers.discard((group, address))
