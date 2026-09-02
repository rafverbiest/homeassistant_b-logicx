"""Button platform — RTC sync; LDM/TSM refresh when check_status is on."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    get_ldm_device_identifiers,
    get_ldm_unique_id,
    get_rtc_device_identifiers,
    get_rtc_unique_id,
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
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])

    entities: list[ButtonEntity] = []
    for addr in addresses:
        t = addr.get("type")
        try:
            if t == ADDRESS_TYPE_RTC:
                entities.append(
                    BLogicxRtcSyncButton(
                        hub=hub,
                        entry_id=entry.entry_id,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"RTC {addr['group']}.{addr['address']}"
                        ),
                    )
                )
            elif t == ADDRESS_TYPE_LDM and addr.get("check_status", False):
                entities.append(
                    BLogicxLdmRefreshButton(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"LDM {addr['group']}.{addr['address']}"
                        ),
                    )
                )
            elif t == ADDRESS_TYPE_TSM and addr.get("check_status", False):
                entities.append(
                    BLogicxTsmRefreshButton(
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
            _LOGGER.error("Skipping invalid button entry %s: %s", addr, err)

    async_add_entities(entities)


class BLogicxRtcSyncButton(ButtonEntity):
    """Push host wall-clock time to the bus RTC (Program sequence)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Synchronize clock"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(
        self,
        hub: BLogicxHub,
        entry_id: str,
        host: str,
        group: int,
        address: int,
        name: str,
    ) -> None:
        self._hub = hub
        self._entry_id = entry_id
        self._group = group
        self._address = address
        self._attr_unique_id = f"{get_rtc_unique_id(host, group, address)}_sync"
        self._attr_device_info = DeviceInfo(
            identifiers=get_rtc_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"RTC {group}.{address}",
        )

    async def async_press(self) -> None:
        manager = self.hass.data[DOMAIN].get(f"{self._entry_id}_rtc")
        if manager is None:
            _LOGGER.error("RTC manager not available")
            return
        await manager.async_sync_key(
            self._group, self._address, reason="manual"
        )


class BLogicxLdmRefreshButton(ButtonEntity):
    """Request LDM reading (Data 0.2 + Select)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Refresh light level"
    _attr_icon = "mdi:refresh"

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
        self._attr_unique_id = f"{get_ldm_unique_id(host, group, address)}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers=get_ldm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"LDM {group}.{address}",
        )

    async def async_press(self) -> None:
        await self._hub.async_request_ldm(self._group, self._address)


class BLogicxTsmRefreshButton(ButtonEntity):
    """Request TSM burst via Status."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"

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
        self._attr_unique_id = f"{get_tsm_unique_id(host, group, address)}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers=get_tsm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"TSM {group}.{address}",
        )

    async def async_press(self) -> None:
        await self._hub.async_request_tsm(self._group, self._address)
