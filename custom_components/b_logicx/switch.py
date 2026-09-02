"""Switch platform for B-Logicx.

Each configured *normal* address on the bus is exposed as a controllable switch.
Shutter/roller covers are handled by the cover platform (CoverEntity), not here.

On/off commands are taken from the per-address config (defaults: Set / Reset).
State is tracked from bus Set/Reset events.

Status-on-startup is serialised via the hub (one Status at a time, wait for
Set/Reset before the next) so concurrent entity setup does not drop replies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADDRESS_TYPE_EXU,
    ADDRESS_TYPE_NORMAL,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    CONF_ADDRESSES,
    CONF_HOST,
    DEFAULT_OFF_COMMAND,
    DEFAULT_ON_COMMAND,
    DOMAIN,
    get_device_identifiers,
    get_entity_unique_id,
)
from .hub import BLogicxHub
from .b_logicx.models import BLXEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up B-Logicx switches from a config entry (normal addresses only)."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]

    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])
    host = entry.data[CONF_HOST]

    entities: list[BLogicxSwitch] = []
    for addr in addresses:
        if addr.get("type") in (
            ADDRESS_TYPE_SHUTTER,
            ADDRESS_TYPE_SFEER,
            ADDRESS_TYPE_EXU,
        ):
            continue
        if addr.get("type", ADDRESS_TYPE_NORMAL) != ADDRESS_TYPE_NORMAL:
            continue
        if "group" not in addr or "address" not in addr:
            continue

        on_command = addr.get("on_command", DEFAULT_ON_COMMAND)
        off_command = addr.get("off_command", DEFAULT_OFF_COMMAND)
        entities.append(
            BLogicxSwitch(
                hub=hub,
                host=host,
                group=addr["group"],
                address=addr["address"],
                name=addr["name"],
                unique_id=get_entity_unique_id(host, addr["group"], addr["address"]),
                on_command=on_command,
                off_command=off_command,
                check_status=addr.get("check_status", False),
            )
        )

    _LOGGER.info("Creating %d B-Logicx switch entities", len(entities))
    async_add_entities(entities)


class BLogicxSwitch(SwitchEntity):
    """Switch representing one normal address on the B-Logicx bus."""

    _attr_should_poll = False

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
        unique_id: str,
        on_command: str,
        off_command: str,
        check_status: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._group = group
        self._address = address
        self._on_command = on_command
        self._off_command = off_command
        self._check_status = check_status
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_is_on = None  # unknown until first event / Status
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for bus events; optionally query Status (serialised on hub)."""
        _LOGGER.debug(
            "Switch %s.%s added to hass (check_status=%s), registering listener",
            self._group,
            self._address,
            self._check_status,
        )
        self._unsub = self._hub.register_listener(
            self._handle_event, self._group, self._address
        )

        if self._check_status:
            # Hub serialises: wait for Set/Reset before the next Status goes out
            is_on = await self._hub.async_request_status(
                self._group, self._address
            )
            if is_on is not None:
                self._attr_is_on = is_on
                self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @property
    def device_info(self):
        """Return device info for this bus address (sub-device under gateway)."""
        return {
            "identifiers": get_device_identifiers(
                self._host, self._group, self._address
            ),
        }

    @callback
    def _handle_event(self, event: BLXEvent) -> None:
        """Handle an event from the bus."""
        if (event.group, event.address) != (self._group, self._address):
            return

        _LOGGER.debug(
            "Event received by switch %s.%s: %s %s.%s",
            self._group,
            self._address,
            event.command,
            event.group,
            event.address,
        )

        if event.command == "Set":
            new_state = True
        elif event.command == "Reset":
            new_state = False
        else:
            return

        if self._attr_is_on != new_state:
            self._attr_is_on = new_state
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hub.async_send(self._on_command, self._group, self._address)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_send(self._off_command, self._group, self._address)
        self._attr_is_on = False
        self.async_write_ha_state()
