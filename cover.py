"""Cover platform for B-Logicx rollers / shutters / blinds.

Each shutter is one CoverEntity backed by exactly two bus addresses:
  - open address  (relay that drives open / up)
  - close address (relay that drives close / down)

B-Logicx datagram pairs (hardcoded — not configurable):
  open  → Toggle(open)  + Reset(close)
  close → Toggle(close) + Reset(open)
  stop  → Toggle(last active direction)

The bus has no end-stop / position feedback. Travel times (open_time /
close_time) estimate when a full open or close has finished.

State machine (same for HA commands and live bus traffic from wall
controls / building blocks):

  idle → (open start) → opening → [open_time] → open
  idle → (close start) → closing → [close_time] → closed
  opening/closing → stop (Reset active / HA stop) → unknown

On reload/restart with check_status only: Status Set/Reset is used once to
assume open/closed (one relay on) or unknown (both off). Status replies do
not start travel timers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    ADDRESS_TYPE_SHUTTER,
    COMMAND_RESET,
    COMMAND_TOGGLE,
    CONF_ADDRESSES,
    CONF_HOST,
    DEFAULT_CLOSE_TIME,
    DEFAULT_OPEN_TIME,
    DOMAIN,
    get_cover_device_identifiers,
    get_cover_unique_id,
)
from .hub import BLogicxHub
from .b_logicx.models import BLXEvent

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up B-Logicx covers from a config entry."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])

    entities: list[BLogicxCover] = []
    for addr in addresses:
        if addr.get("type") != ADDRESS_TYPE_SHUTTER:
            continue
        try:
            entities.append(
                BLogicxCover(
                    hub=hub,
                    host=host,
                    name=addr.get("name", "Cover"),
                    open_group=int(addr["open_group"]),
                    open_address=int(addr["open_address"]),
                    close_group=int(addr["close_group"]),
                    close_address=int(addr["close_address"]),
                    open_time=float(
                        addr.get("open_time", DEFAULT_OPEN_TIME) or DEFAULT_OPEN_TIME
                    ),
                    close_time=float(
                        addr.get("close_time", DEFAULT_CLOSE_TIME)
                        or DEFAULT_CLOSE_TIME
                    ),
                    check_status=addr.get("check_status", False),
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error(
                "Skipping invalid shutter config entry %s: %s", addr, err
            )

    _LOGGER.info(
        "Creating %d B-Logicx cover entities: %s",
        len(entities),
        ", ".join(e.name for e in entities) or "(none)",
    )
    if not entities:
        shutter_like = [a for a in addresses if a.get("type") == ADDRESS_TYPE_SHUTTER]
        if shutter_like:
            _LOGGER.warning(
                "Found %d type=shutter entries in config but created 0 covers: %s",
                len(shutter_like),
                shutter_like,
            )
        else:
            _LOGGER.debug(
                "No shutter entries in config (%d total addresses)",
                len(addresses),
            )
    async_add_entities(entities)


class BLogicxCover(CoverEntity):
    """Cover representing a B-Logicx open/close relay pair.

    Travel timers apply to both HA services and live bus Set/Reset from
    physical controls. Status at startup only snapshots open/closed/unknown.
    """

    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        name: str,
        open_group: int,
        open_address: int,
        close_group: int,
        close_address: int,
        open_time: float = DEFAULT_OPEN_TIME,
        close_time: float = DEFAULT_CLOSE_TIME,
        check_status: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._open_group = open_group
        self._open_address = open_address
        self._close_group = close_group
        self._close_address = close_address
        self._open_time = max(0.1, float(open_time))
        self._close_time = max(0.1, float(close_time))
        self._check_status = check_status

        self._attr_name = name
        self._attr_unique_id = get_cover_unique_id(
            host, open_group, open_address, close_group, close_address
        )

        self._open_relay_on: bool | None = None
        self._close_relay_on: bool | None = None
        self._last_direction: str | None = None
        # HA motion: "open" | "close" | None
        self._motion: str | None = None
        # True=closed, False=open, None=unknown
        self._attr_is_closed: bool | None = None
        self._travel_unsub: Callable[[], None] | None = None
        # True only while processing check_status Status queries
        self._status_probe = False

        self._unsub_open: Callable[[], None] | None = None
        self._unsub_close: Callable[[], None] | None = None

    @property
    def device_info(self):
        return {
            "identifiers": get_cover_device_identifiers(
                self._host,
                self._open_group,
                self._open_address,
                self._close_group,
                self._close_address,
            ),
            "name": self._attr_name,
            "manufacturer": "B-Logicx",
            "model": (
                f"Cover {self._open_group}.{self._open_address} / "
                f"{self._close_group}.{self._close_address}"
            ),
        }

    @property
    def is_opening(self) -> bool:
        return self._motion == "open"

    @property
    def is_closing(self) -> bool:
        return self._motion == "close"

    async def async_added_to_hass(self) -> None:
        self._unsub_open = self._hub.register_listener(
            self._handle_open_event, self._open_group, self._open_address
        )
        self._unsub_close = self._hub.register_listener(
            self._handle_close_event, self._close_group, self._close_address
        )

        if self._check_status:
            self._status_probe = True
            try:
                open_on = await self._hub.async_request_status(
                    self._open_group, self._open_address
                )
                close_on = await self._hub.async_request_status(
                    self._close_group, self._close_address
                )
                if open_on is not None:
                    self._open_relay_on = open_on
                if close_on is not None:
                    self._close_relay_on = close_on
            finally:
                self._status_probe = False
            # Reload snapshot only — not the live travel machine
            self._apply_status_snapshot()
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_travel_timer()
        if self._unsub_open:
            self._unsub_open()
        if self._unsub_close:
            self._unsub_close()

    def _cancel_travel_timer(self) -> None:
        if self._travel_unsub is not None:
            self._travel_unsub()
            self._travel_unsub = None

    def _apply_status_snapshot(self) -> None:
        """After check_status only: one relay on → open/closed; both off → unknown."""
        open_on = self._open_relay_on
        close_on = self._close_relay_on
        if open_on is True and close_on is not True:
            self._attr_is_closed = False
            _LOGGER.debug(
                "Cover %s: Status snapshot → open (open relay on)", self._attr_name
            )
        elif close_on is True and open_on is not True:
            self._attr_is_closed = True
            _LOGGER.debug(
                "Cover %s: Status snapshot → closed (close relay on)",
                self._attr_name,
            )
        elif open_on is False and close_on is False:
            self._attr_is_closed = None
            _LOGGER.debug(
                "Cover %s: Status snapshot → unknown (both relays off)",
                self._attr_name,
            )

    def _begin_travel(self, direction: str) -> None:
        """Enter opening/closing and schedule full-travel open/closed."""
        if direction not in ("open", "close"):
            return
        # Already moving this way (e.g. HA command then bus echo): keep timer
        if self._motion == direction:
            return
        # Reverse while moving: end previous travel cleanly then start new
        if self._motion is not None and self._motion != direction:
            self._cancel_travel_timer()

        self._last_direction = direction
        self._motion = direction
        self._attr_is_closed = None
        seconds = self._open_time if direction == "open" else self._close_time
        self._schedule_travel_complete(direction, seconds)
        _LOGGER.debug(
            "Cover %s: begin %s travel (%.1fs)",
            self._attr_name,
            direction,
            seconds,
        )

    def _end_travel_stopped(self) -> None:
        """Stop mid-travel: unknown position."""
        self._cancel_travel_timer()
        self._motion = None
        self._attr_is_closed = None
        _LOGGER.debug("Cover %s: stop → unknown", self._attr_name)

    def _schedule_travel_complete(self, direction: str, seconds: float) -> None:
        self._cancel_travel_timer()

        @callback
        def _done(_now) -> None:
            self._travel_unsub = None
            if self._motion != direction:
                return
            self._motion = None
            if direction == "open":
                self._attr_is_closed = False
                _LOGGER.debug(
                    "Cover %s: open travel (%.1fs) elapsed → open",
                    self._attr_name,
                    seconds,
                )
            else:
                self._attr_is_closed = True
                _LOGGER.debug(
                    "Cover %s: close travel (%.1fs) elapsed → closed",
                    self._attr_name,
                    seconds,
                )
            self.async_write_ha_state()

        self._travel_unsub = async_call_later(self.hass, seconds, _done)

    def _on_relay_change(self, which: str, is_on: bool) -> None:
        """Update HA motion from live bus Set/Reset (not during Status probe)."""
        if which == "open":
            self._open_relay_on = is_on
        else:
            self._close_relay_on = is_on

        if self._status_probe:
            return

        if is_on:
            direction = which  # "open" or "close"
            # Opposite direction Set while moving → reverse
            if self._motion is not None and self._motion != direction:
                self._end_travel_stopped()
            self._begin_travel(direction)
            return

        # Relay off (Reset)
        if self._motion == which:
            # Active direction powered down → mid-stop (or end of pulse)
            self._end_travel_stopped()

    @callback
    def _handle_open_event(self, event: BLXEvent) -> None:
        if (event.group, event.address) != (self._open_group, self._open_address):
            return
        if event.command == "Set":
            self._on_relay_change("open", True)
        elif event.command == "Reset":
            self._on_relay_change("open", False)
        else:
            return
        self.async_write_ha_state()

    @callback
    def _handle_close_event(self, event: BLXEvent) -> None:
        if (event.group, event.address) != (self._close_group, self._close_address):
            return
        if event.command == "Set":
            self._on_relay_change("close", True)
        elif event.command == "Reset":
            self._on_relay_change("close", False)
        else:
            return
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open: Toggle open + Reset close; travel timer for HA state."""
        await self._hub.async_send(
            COMMAND_RESET, self._close_group, self._close_address
        )
        await self._hub.async_send(
            COMMAND_TOGGLE, self._open_group, self._open_address
        )
        self._open_relay_on = True
        self._close_relay_on = False
        self._begin_travel("open")
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close: Toggle close + Reset open; travel timer for HA state."""
        await self._hub.async_send(
            COMMAND_RESET, self._open_group, self._open_address
        )
        await self._hub.async_send(
            COMMAND_TOGGLE, self._close_group, self._close_address
        )
        self._close_relay_on = True
        self._open_relay_on = False
        self._begin_travel("close")
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop: Toggle active direction (or Reset both if unknown)."""
        direction = self._active_direction()
        if direction == "open":
            await self._hub.async_send(
                COMMAND_TOGGLE, self._open_group, self._open_address
            )
            self._open_relay_on = False
        elif direction == "close":
            await self._hub.async_send(
                COMMAND_TOGGLE, self._close_group, self._close_address
            )
            self._close_relay_on = False
        else:
            await self._hub.async_send(
                COMMAND_RESET, self._open_group, self._open_address
            )
            await self._hub.async_send(
                COMMAND_RESET, self._close_group, self._close_address
            )
            self._open_relay_on = False
            self._close_relay_on = False

        self._end_travel_stopped()
        self.async_write_ha_state()

    def _active_direction(self) -> str | None:
        if self._motion in ("open", "close"):
            return self._motion
        if self._open_relay_on is True:
            return "open"
        if self._close_relay_on is True:
            return "close"
        return self._last_direction
