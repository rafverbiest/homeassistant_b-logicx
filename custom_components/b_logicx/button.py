"""Buttons that ask a module to do something now.

Every RTC gets a sync button. An LDM, a TSM, or a WSM gets a refresh button
only when check_status is on, the same flag that asks for a reading at startup.
A BL-BM8 gets eight chime buttons and a stop button. A press sends that pair
and does not stay on.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADDRESS_TYPE_BM8,
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_TSM,
    ADDRESS_TYPE_WSM,
    BM8_CHIME_COUNT,
    BM8_STOP_DATA_ADDRESS,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    bm8_chime_data_address,
    get_bm8_device_identifiers,
    get_bm8_unique_id,
    get_ldm_device_identifiers,
    get_ldm_unique_id,
    get_rtc_device_identifiers,
    get_rtc_unique_id,
    get_tsm_device_identifiers,
    get_tsm_unique_id,
    get_wsm_device_identifiers,
    get_wsm_unique_id,
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
            elif t == ADDRESS_TYPE_WSM and addr.get("check_status", False):
                entities.append(
                    BLogicxWsmRefreshButton(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"WSM {addr['group']}.{addr['address']}"
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
            elif t == ADDRESS_TYPE_BM8:
                group = int(addr["group"])
                address = int(addr["address"])
                name = addr.get("name", f"Chime {group}.{address}")
                for chime in range(1, BM8_CHIME_COUNT + 1):
                    entities.append(
                        BLogicxBm8Button(
                            hub=hub,
                            host=host,
                            group=group,
                            address=address,
                            name=name,
                            data_address=bm8_chime_data_address(chime),
                            chime=chime,
                        )
                    )
                entities.append(
                    BLogicxBm8Button(
                        hub=hub,
                        host=host,
                        group=group,
                        address=address,
                        name=name,
                        data_address=BM8_STOP_DATA_ADDRESS,
                        chime=None,
                    )
                )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid button entry %s: %s", addr, err)

    async_add_entities(entities)


class BLogicxRtcSyncButton(ButtonEntity):
    """Push host wall-clock time to the bus RTC (Program sequence)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "sync_clock"
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
    _attr_translation_key = "refresh_light"
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


class BLogicxWsmRefreshButton(ButtonEntity):
    """Request a wind reading (Data 0.2 + Select)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "refresh_wind"
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
        self._attr_unique_id = f"{get_wsm_unique_id(host, group, address)}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers=get_wsm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"BL-WSM {group}.{address}",
        )

    async def async_press(self) -> None:
        await self._hub.async_request_wsm(self._group, self._address)


class BLogicxTsmRefreshButton(ButtonEntity):
    """Request TSM burst via Status."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "refresh_temperature"
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


class BLogicxBm8Button(ButtonEntity):
    """One BL-BM8 chime, or the stop control for that module.

    chime is 1 through 8. None is stop. The button does not stay on: the
    module never says when the sound has finished.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
        data_address: int,
        chime: int | None,
    ) -> None:
        self._hub = hub
        self._group = group
        self._address = address
        self._data_address = data_address
        bm8_id = get_bm8_unique_id(host, group, address)
        if chime is None:
            self._attr_translation_key = "chime_stop"
            self._attr_icon = "mdi:stop"
            self._attr_unique_id = f"{bm8_id}_stop"
        else:
            self._attr_translation_key = "chime"
            self._attr_translation_placeholders = {"number": str(chime)}
            self._attr_icon = "mdi:bell-ring"
            self._attr_unique_id = f"{bm8_id}_chime_{chime}"
        self._attr_device_info = DeviceInfo(
            identifiers=get_bm8_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"BL-BM8 {group}.{address}",
        )

    async def async_press(self) -> None:
        await self._hub.async_sound_bm8(
            self._group, self._address, self._data_address
        )
