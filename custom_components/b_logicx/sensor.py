"""Sensors that only display what the bus already said.

One RTC shows when this integration last wrote the clock. One LDM shows the
light level in percent. One TSM becomes the temperature, the active preset,
the active setpoint, and one cached setpoint for each preset name. One WSM
shows the wind speed in km/h.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .b_logicx.measure import (
    LdmReading,
    TsmReading,
    WsmReading,
    wsm_should_confirm_quiet,
)
from .const import (
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_TSM,
    ADDRESS_TYPE_WSM,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    TSM_PRESET_LABELS,
    measurement_from_ha_state,
    text_from_ha_state,
    whole_number_from_ha_state,
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

# How often to look at a stuck breeze. The ask itself waits a quarter hour.
_WSM_QUIET_CHECK_S = 60.0


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
            elif t == ADDRESS_TYPE_WSM:
                entities.append(
                    BLogicxWsmWindSensor(
                        hub=hub,
                        host=host,
                        group=int(addr["group"]),
                        address=int(addr["address"]),
                        name=addr.get(
                            "name", f"WSM {addr['group']}.{addr['address']}"
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
                        check_status=check,
                    )
                )
                entities.append(
                    BLogicxTsmActiveSetpointSensor(
                        hub=hub, host=host, group=g, address=a, name=name,
                        check_status=check,
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
                            check_status=check,
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


class BLogicxLdmLightSensor(SensorEntity, RestoreEntity):
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
            return
        await _restore_number(self, measurement_from_ha_state, raw_attr="raw")

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


# ----- WSM -----------------------------------------------------------------


class BLogicxWsmWindSensor(SensorEntity, RestoreEntity):
    """WSM wind speed in km/h (from Value 14 + System)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "wind_speed"
    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:weather-windy"

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
        self._updated_at: float | None = None
        self._quiet_stop = asyncio.Event()
        self._quiet_task: asyncio.Task | None = None
        self._attr_unique_id = f"{get_wsm_unique_id(host, group, address)}_wind"
        self._attr_device_info = DeviceInfo(
            identifiers=get_wsm_device_identifiers(host, group, address),
            name=name,
            manufacturer="B-Logicx",
            model=f"WSM {group}.{address}",
        )
        self._attr_native_value = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if self._raw is not None:
            attrs["raw"] = self._raw
        return attrs

    def _show_reading(self, reading: WsmReading) -> None:
        self._raw = reading.raw
        self._attr_native_value = reading.kmh
        self._updated_at = time.monotonic()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_reading(reading: WsmReading) -> None:
            self._show_reading(reading)

        self._unsub = self._hub.register_wsm(self._group, self._address, _on_reading)
        if self._check_status:
            reading = await self._hub.async_request_wsm(self._group, self._address)
            if reading is not None:
                _on_reading(reading)
        else:
            restored = await _restore_number(
                self, whole_number_from_ha_state, raw_attr="raw"
            )
            if restored:
                # Age the quiet check from this start, so a restored breeze
                # can still be asked again. Zero stays alone.
                self._updated_at = time.monotonic()
        # Startup waits on async_create_task. This loop never ends.
        self._quiet_task = self.hass.async_create_background_task(
            self._confirm_quiet(),
            name=f"b_logicx_wsm_quiet_{self._group}_{self._address}",
        )

    async def _confirm_quiet(self) -> None:
        """Ask again when a non-zero speed has sat still. A calm zero is left alone."""
        while not self._quiet_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._quiet_stop.wait(), timeout=_WSM_QUIET_CHECK_S
                )
                return
            except asyncio.TimeoutError:
                pass
            updated = self._updated_at
            if updated is None:
                continue
            age = time.monotonic() - updated
            if not wsm_should_confirm_quiet(self._attr_native_value, age):
                continue
            reading = await self._hub.async_request_wsm(self._group, self._address)
            if self._quiet_stop.is_set():
                return
            if reading is not None:
                self._show_reading(reading)
            else:
                # No answer. Wait the full quiet interval before asking again.
                self._updated_at = time.monotonic()

    async def async_will_remove_from_hass(self) -> None:
        self._quiet_stop.set()
        if self._quiet_task is not None and not self._quiet_task.done():
            self._quiet_task.cancel()
            self._quiet_task = None
        if self._unsub:
            self._unsub()
            self._unsub = None


# ----- TSM helpers ---------------------------------------------------------


class _TsmEntityBase(SensorEntity, RestoreEntity):
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
        check_status: bool = False,
    ) -> None:
        self._hub = hub
        self._group = group
        self._address = address
        self._check_status = check_status
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
        super().__init__(
            hub, host, group, address, name, "temperature", check_status=check_status
        )
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
            return
        last = await _restore_number(self, measurement_from_ha_state)
        if last is None:
            return
        raw = last.attributes.get("value_address")
        if isinstance(raw, int) and not isinstance(raw, bool):
            self._value_address = raw
            self.async_write_ha_state()


class BLogicxTsmActivePresetSensor(_TsmEntityBase):
    _attr_translation_key = "active_preset"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, hub, host, group, address, name, check_status: bool = False):
        super().__init__(
            hub, host, group, address, name, "preset", check_status=check_status
        )
        self._attr_native_value = None

    def _apply_reading(self, reading: TsmReading) -> None:
        if reading.preset_name is not None:
            self._attr_native_value = reading.preset_name

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._check_status:
            return
        text = text_from_ha_state(await _last_state_text(self))
        if text is None:
            return
        self._attr_native_value = text
        self.async_write_ha_state()


class BLogicxTsmActiveSetpointSensor(_TsmEntityBase):
    _attr_translation_key = "active_setpoint"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, hub, host, group, address, name, check_status: bool = False):
        super().__init__(
            hub,
            host,
            group,
            address,
            name,
            "active_setpoint",
            check_status=check_status,
        )
        self._attr_native_value = None

    def _apply_reading(self, reading: TsmReading) -> None:
        if reading.preset_setpoint is not None:
            self._attr_native_value = reading.preset_setpoint

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._check_status:
            return
        await _restore_number(self, measurement_from_ha_state)


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
        check_status: bool = False,
    ):
        super().__init__(
            hub,
            host,
            group,
            address,
            name,
            f"setpoint_{preset_index}",
            check_status=check_status,
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._check_status:
            return
        await _restore_number(self, measurement_from_ha_state)


async def _last_state_text(entity: RestoreEntity) -> str | None:
    """Previous state string, or None when this entity has nothing saved."""
    last = await entity.async_get_last_state()
    if last is None:
        return None
    return last.state


async def _restore_number(entity: RestoreEntity, parse, raw_attr: str | None = None):
    """Show the last number again. Returns the state when a number was kept.

    check_status is the caller's concern. A missing or unknown state is left
    unknown. An optional integer attribute, such as raw, is kept with it.
    """
    last = await entity.async_get_last_state()
    if last is None:
        return None
    value = parse(last.state)
    if value is None:
        return None
    entity._attr_native_value = value
    if raw_attr is not None:
        raw = last.attributes.get(raw_attr)
        if isinstance(raw, int) and not isinstance(raw, bool):
            entity._raw = raw
    entity.async_write_ha_state()
    return last
