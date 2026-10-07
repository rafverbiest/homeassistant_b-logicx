"""Switch platform for an RLM or a SoftM.

- A tracked SoftM (this is the Virtual Status Module): Home Assistant always sends
  Set and Reset, restores the last on/off or uses default_state, and does not
  ask Status.

- An untracked SoftM, and an RLM, send the configured on and off
  commands and may ask Status at startup. Either way, a Set or Reset heard on
  the bus is what updates the switch.

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
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ADDRESS_TYPE_READONLY,
    is_softm_address,
    is_switch_address,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    CONF_ADDRESSES,
    CONF_HOST,
    DEFAULT_OFF_COMMAND,
    DEFAULT_ON_COMMAND,
    DOMAIN,
    on_off_from_ha_state,
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
    """Set up B-Logicx switches from a config entry (RLM and SoftM)."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]

    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])
    host = entry.data[CONF_HOST]

    entities: list[BLogicxSwitch] = []
    for addr in addresses:
        if addr.get("type") in (
            ADDRESS_TYPE_SHUTTER,
            ADDRESS_TYPE_SFEER,
            ADDRESS_TYPE_READONLY,
        ):
            continue
        if not is_switch_address(addr):
            continue
        if "group" not in addr or "address" not in addr:
            continue

        on_command = addr.get("on_command", DEFAULT_ON_COMMAND)
        off_command = addr.get("off_command", DEFAULT_OFF_COMMAND)
        softm = is_softm_address(addr)
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
                check_status=False if softm else addr.get("check_status", False),
                softm_tracking=softm,
                persist_state=bool(addr.get("persist_state", softm)),
                default_state=bool(addr.get("default_state", False)),
            )
        )

    _LOGGER.info("Creating %d B-Logicx switch entities", len(entities))
    async_add_entities(entities)


class BLogicxSwitch(SwitchEntity, RestoreEntity):
    """Switch representing one RLM or SoftM address on the B-Logicx bus."""

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
        softm_tracking: bool = False,
        persist_state: bool = False,
        default_state: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._group = group
        self._address = address
        self._on_command = on_command
        self._off_command = off_command
        self._check_status = check_status
        self._softm_tracking = softm_tracking
        self._persist_state = persist_state
        self._default_state = default_state
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_is_on = None  # unknown until first event / Status / restore
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for bus events; seed SoftM or query Status."""
        self._unsub = self._hub.register_listener(
            self._handle_event, self._group, self._address
        )

        if self._softm_tracking:
            restored: bool | None = None
            if self._persist_state:
                last = await self.async_get_last_state()
                if last is not None and last.state in ("on", "off"):
                    restored = last.state == "on"
            if restored is not None:
                self._attr_is_on = restored
            else:
                self._attr_is_on = self._default_state
            self._hub.softm_seed(self._group, self._address, bool(self._attr_is_on))
            self.async_write_ha_state()
            return

        if not self._check_status:
            # No Status probe: show the last known on/off so the entity is not
            # unknown after a restart. Bus Set/Reset still updates it later.
            last = await self.async_get_last_state()
            restored = on_off_from_ha_state(last.state if last is not None else None)
            if restored is not None:
                self._attr_is_on = restored
                self.async_write_ha_state()
            return

        if self._check_status:
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
        # SoftM tracking answers Toggle from the bus; HA must send Set/Reset
        # so we do not double-flip when on_command is Toggle.
        cmd = "Set" if self._softm_tracking else self._on_command
        await self._hub.async_send(cmd, self._group, self._address)
        self._attr_is_on = True
        if self._softm_tracking:
            self._hub.softm_seed(self._group, self._address, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        cmd = "Reset" if self._softm_tracking else self._off_command
        await self._hub.async_send(cmd, self._group, self._address)
        self._attr_is_on = False
        if self._softm_tracking:
            self._hub.softm_seed(self._group, self._address, False)
        self.async_write_ha_state()
