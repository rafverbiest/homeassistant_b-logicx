"""Sensor platform — RTC last sync, LDM light %, TSM temperature / presets."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .b_logicx.measure import LdmReading, TsmReading
from .const import (
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    TSM_PRESET_LABELS,
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

    entities: list[SensorEntity] = []
    for addr in addresses:
        t = addr.get("type")
        try:
            if t == ADDRESS_TYPE_RTC:
                entities.append(
                    BLogicxRtcLastSyncSensor(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"RTC {addr['group']}.{addr['address']}"
                        ),
                    )
                )
            elif t == ADDRESS_TYPE_LDM:
                entities.append(
                    BLogicxLdmLightSensor(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"LDM {addr['group']}.{addr['address']}"
                        ),
                        check_status=bool(addr.get("check_status", False)),
                    )
                )
            elif t == ADDRESS_TYPE_TSM:
                g, a = int(addr["group"]), int(addr["address"])
                name = addr.get("name", f"TSM {g}.{a}")
                check = bool(addr.get("check_status", False))
                entities.append(
                    BLogicxTsmTemperatureSensor(
                        hub=hub, host=host, group=g, address=a, name=name,
                        check_status=check,
                    )
                )
                entities.append(
                    BLogicxTsmActivePresetSensor(
                        hub=hub, host=host, group=g, address=a, name=name,
                    )
                )
                entities.append(
                    BLogicxTsmActiveSetpointSensor(
                        hub=hub, host=host, group=g, address=a, name=name,
                    )
                )
                for idx, label in enumerate(TSM_PRESET_LABELS, start=1):
                    entities.append(
                        BLogicxTsmCachedSetpointSensor(
                            hub=hub,
                            host=host,
                            group=g,
                            address=a,
                            name=name,
                            preset_index=idx,
                            preset_label=label,
                        )
                    )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid sensor entry %s: %s", addr, err)

    async_add_entities(entities)


# ----- RTC -----------------------------------------------------------------


class BLogicxRtcLastSyncSensor(SensorEntity):
    """When the integration last pushed time to this RTC."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "last_sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-outline"

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
        self._attr_unique_id = f"{get_rtc_unique_id(host, group, address)}_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers=get_rtc_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"RTC {group}.{address}",
        )
        self._attr_native_value = hub.rtc_last_sync.get((group, address))

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_sync(group: int, address: int, when: Any) -> None:
            if group != self._group or address != self._address:
                return
            self._attr_native_value = when
            self.async_write_ha_state()

        self._unsub = self._hub.register_rtc_sync_callback(_on_sync)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


# ----- LDM -----------------------------------------------------------------


class BLogicxLdmLightSensor(SensorEntity):
    """LDM light level as percent (from Value+System pair)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "light_level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:brightness-6"

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
        self._group = group
        self._address = address
        self._check_status = check_status
        self._unsub = None
        self._raw: int | None = None
        self._attr_unique_id = f"{get_ldm_unique_id(host, group, address)}_light"
        self._attr_device_info = DeviceInfo(
            identifiers=get_ldm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"LDM {group}.{address}",
        )
        self._attr_native_value = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self._raw is not None:
            attrs["raw"] = self._raw
        return attrs

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_reading(reading: LdmReading) -> None:
            self._raw = reading.raw
            self._attr_native_value = round(reading.percent, 2)
            self.async_write_ha_state()

        self._unsub = self._hub.register_ldm(self._group, self._address, _on_reading)
        if self._check_status:
            reading = await self._hub.async_request_ldm(self._group, self._address)
            if reading is not None:
                _on_reading(reading)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


# ----- TSM helpers ---------------------------------------------------------


class _TsmEntityBase(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
        uid_suffix: str,
    ) -> None:
        self._hub = hub
        self._group = group
        self._address = address
        self._unsub = None
        self._attr_unique_id = f"{get_tsm_unique_id(host, group, address)}_{uid_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers=get_tsm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"TSM {group}.{address}",
        )

    def _apply_reading(self, reading: TsmReading) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_reading(reading: TsmReading) -> None:
            self._apply_reading(reading)
            self.async_write_ha_state()

        self._unsub = self._hub.register_tsm(self._group, self._address, _on_reading)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


class BLogicxTsmTemperatureSensor(_TsmEntityBase):
    """Measured temperature from Value 11.x (address/2 °C, offset included)."""

    _attr_translation_key = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub, host, group, address, name, check_status: bool = False):
        super().__init__(hub, host, group, address, name, "temperature")
        self._check_status = check_status
        self._attr_native_value = None
        self._value_address: int | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self._value_address is not None:
            attrs["value_address"] = self._value_address
        return attrs

    def _apply_reading(self, reading: TsmReading) -> None:
        self._attr_native_value = reading.temperature_c
        if reading.value_address is not None:
            self._value_address = reading.value_address

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._check_status:
            reading = await self._hub.async_request_tsm(self._group, self._address)
            if reading is not None:
                self._apply_reading(reading)
                self.async_write_ha_state()


class BLogicxTsmActivePresetSensor(_TsmEntityBase):
    _attr_translation_key = "active_preset"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, hub, host, group, address, name):
        super().__init__(hub, host, group, address, name, "preset")
        self._attr_native_value = None

    def _apply_reading(self, reading: TsmReading) -> None:
        if reading.preset_name is not None:
            self._attr_native_value = reading.preset_name


class BLogicxTsmActiveSetpointSensor(_TsmEntityBase):
    _attr_translation_key = "active_setpoint"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, hub, host, group, address, name):
        super().__init__(hub, host, group, address, name, "active_setpoint")
        self._attr_native_value = None

    def _apply_reading(self, reading: TsmReading) -> None:
        if reading.preset_setpoint is not None:
            self._attr_native_value = reading.preset_setpoint


class BLogicxTsmCachedSetpointSensor(_TsmEntityBase):
    """Last-seen setpoint for one fixed preset (when that preset was active)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        hub,
        host,
        group,
        address,
        name,
        preset_index: int,
        preset_label: str,
    ):
        super().__init__(
            hub, host, group, address, name, f"setpoint_{preset_index}"
        )
        self._preset_index = preset_index
        self._attr_name = f"{preset_label} setpoint"
        self._attr_native_value = None

    def _apply_reading(self, reading: TsmReading) -> None:
        if reading.preset_index == self._preset_index and reading.preset_setpoint is not None:
            self._attr_native_value = reading.preset_setpoint
        # Also pull from hub cache if available
        cached = self._hub._measure.preset_setpoint_cache.get(self._preset_index)
        if cached is not None:
            self._attr_native_value = cached
