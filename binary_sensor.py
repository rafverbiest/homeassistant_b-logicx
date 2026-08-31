"""Binary sensor platform for B-Logicx EXU (listen-only inputs).

EXU addresses are observed only: Set → on, Reset → off. The integration may
send Status when check_status is enabled, but never Set/Reset/Toggle/Dimmer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .b_logicx.measure import TsmReading
from .b_logicx.models import BLXEvent
from .const import (
    ADDRESS_TYPE_EXU,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    get_device_identifiers,
    get_entity_unique_id,
    get_tsm_device_identifiers,
    get_tsm_unique_id,
)
from .hub import BLogicxHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up B-Logicx EXU and TSM heat-requested binary sensors."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])

    entities: list[BinarySensorEntity] = []
    for addr in addresses:
        t = addr.get("type")
        try:
            if t == ADDRESS_TYPE_EXU:
                entities.append(
                    BLogicxExuSensor(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"EXU {addr['group']}.{addr['address']}"
                        ),
                        check_status=addr.get("check_status", False),
                    )
                )
            elif t == ADDRESS_TYPE_TSM:
                entities.append(
                    BLogicxTsmHeatRequestedSensor(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"TSM {addr['group']}.{addr['address']}"
                        ),
                    )
                )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid binary_sensor entry %s: %s", addr, err)

    async_add_entities(entities)


class BLogicxExuSensor(BinarySensorEntity):
    """Listen-only bus address (EXU / input)."""

    _attr_should_poll = False

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
        check_status: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._group = group
        self._address = address
        self._check_status = check_status
        self._attr_name = name
        self._attr_unique_id = get_entity_unique_id(host, group, address)
        self._attr_is_on: bool | None = None
        self._unsub: Callable[[], None] | None = None

    @property
    def device_info(self):
        return {
            "identifiers": get_device_identifiers(
                self._host, self._group, self._address
            ),
        }

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.register_listener(
            self._handle_event, self._group, self._address
        )
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

    @callback
    def _handle_event(self, event: BLXEvent) -> None:
        if (event.group, event.address) != (self._group, self._address):
            return
        if event.command == "Set":
            self._attr_is_on = True
        elif event.command == "Reset":
            self._attr_is_on = False
        else:
            return
        self.async_write_ha_state()


class BLogicxTsmHeatRequestedSensor(BinarySensorEntity):
    """TSM heat requested (System 15.48 / 15.16) — not plant on/off."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Heat requested"
    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_icon = "mdi:radiator"

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
    ) -> None:
        self._hub = hub
        self._group = group
        self._address = address
        self._unsub = None
        self._attr_unique_id = f"{get_tsm_unique_id(host, group, address)}_heat_req"
        self._attr_device_info = DeviceInfo(
            identifiers=get_tsm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"TSM {group}.{address}",
        )
        self._attr_is_on: bool | None = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_reading(reading: TsmReading) -> None:
            if reading.heat_requested is not None:
                self._attr_is_on = reading.heat_requested
                self.async_write_ha_state()

        self._unsub = self._hub.register_tsm(self._group, self._address, _on_reading)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
