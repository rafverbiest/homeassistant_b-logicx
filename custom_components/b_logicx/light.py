"""One light per dimmer: master on/off, and a slider for the percent.

On and off send Dimmer on this address, then Dimmer <group>.220. The
dimmer answers with Set or Reset, and that answer is the on/off state.
The slider sends Data 0.<percent> and then Timer to this dimmer. A Sfeer
in the group clears the known percent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .b_logicx.dimmer import (
    DIMMER_PERCENT_MAX,
    DimmerConfig,
    DimmerView,
    brightness_to_percent,
    percent_to_brightness,
)
from .const import (
    ADDRESS_TYPE_DIMMER,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    get_dimmer_device_identifiers,
    get_dimmer_unique_id,
    on_off_from_ha_state,
)
from .hub import BLogicxHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one light for each configured dimmer."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])

    entities: list[BLogicxDimmer] = []
    for addr in addresses:
        if addr.get("type") != ADDRESS_TYPE_DIMMER:
            continue
        try:
            group = int(addr["group"])
            address = int(addr["address"])
            entities.append(
                BLogicxDimmer(
                    hub=hub,
                    host=host,
                    config=DimmerConfig(
                        group=group,
                        address=address,
                        remembers_level=bool(addr.get("remembers_level", False)),
                        participates_in_moods=bool(
                            addr.get("participates_in_moods", True)
                        ),
                    ),
                    name=addr.get("name") or f"Dimmer {group}.{address}",
                    check_status=bool(addr.get("check_status", False)),
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid dimmer entry %s: %s", addr, err)

    _LOGGER.info("Creating %d B-Logicx dimmer light(s)", len(entities))
    async_add_entities(entities)


class _DimmerLevelStored(ExtraStoredData):
    """Last percent, kept while the lamp is off and brightness is empty."""

    def __init__(self, percent: int | None) -> None:
        self.percent = percent

    def as_dict(self) -> dict[str, int | None]:
        return {"percent": self.percent}

    @classmethod
    def from_dict(cls, data: dict) -> "_DimmerLevelStored | None":
        if not isinstance(data, dict) or "percent" not in data:
            return None
        raw = data.get("percent")
        if raw is None:
            return cls(None)
        try:
            percent = int(raw)
        except (TypeError, ValueError):
            return None
        if percent < 0 or percent > DIMMER_PERCENT_MAX:
            return None
        return cls(percent)


class BLogicxDimmer(LightEntity, RestoreEntity):
    """A dimmer. The last on/off and percent come back after a restart.

    check_status asks the bus for on or off. The saved percent stays,
    because Status cannot report a level.
    """

    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        config: DimmerConfig,
        name: str,
        check_status: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._config = config
        self._group = config.group
        self._address = config.address
        self._check_status = check_status
        self._attr_name = name
        self._attr_unique_id = get_dimmer_unique_id(host, config.group, config.address)
        self._attr_is_on = None
        self._attr_brightness = None
        self._attr_color_mode = None
        # Last percent the card showed. An off lamp clears brightness, so
        # this is what restore writes beside the state.
        self._level: int | None = None
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Listen for bus updates. Restore the last level, or ask Status."""
        self._unsub = self._hub.register_dimmer(self._config, self._handle_view)
        last = await self.async_get_last_state()
        extra = await self.async_get_last_extra_data()
        percent = _percent_from_restore(last, extra)
        saved_on = on_off_from_ha_state(last.state if last is not None else None)
        if self._check_status:
            # Read the percent first. The Status reply may replace it with
            # 100% or clear it before this method continues.
            self._level = percent
            reported = await self._hub.async_request_status(
                self._group, self._address
            )
            if reported is None:
                reported = saved_on
            elif percent is None:
                return
            if reported is None:
                return
            self._level = percent
            self._hub.dimmer_seed(self._group, self._address, reported, percent)
            self._show(self._hub.dimmer_view(self._group, self._address))
            self.async_write_ha_state()
            return
        if saved_on is not None:
            self._level = percent
            self._hub.dimmer_seed(self._group, self._address, saved_on, percent)
        self._show(self._hub.dimmer_view(self._group, self._address))
        self.async_write_ha_state()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Percent kept beside the state, including while the lamp is off."""
        return _DimmerLevelStored(self._level)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self):
        """Device registry link. The device itself is created at setup."""
        return {
            "identifiers": get_dimmer_device_identifiers(
                self._host, self._group, self._address
            ),
        }

    @callback
    def _handle_view(self, view: DimmerView) -> None:
        self._show(view)
        self.async_write_ha_state()

    def _show(self, view: DimmerView) -> None:
        self._attr_is_on = view.is_on
        if view.percent is not None:
            self._level = view.percent
        elif view.is_on is True:
            # Hold or Sfeer dropped the level. Do not keep a stale number.
            self._level = None
        if view.is_on and view.percent is not None:
            self._attr_brightness = percent_to_brightness(view.percent)
            self._attr_color_mode = ColorMode.BRIGHTNESS
        elif view.is_on:
            self._attr_brightness = None
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_brightness = None
            self._attr_color_mode = None

    async def async_turn_on(self, **kwargs) -> None:
        """Slider movement sends a percent. A plain on sends the tap pair."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            await self._hub.async_set_dimmer_level(
                self._group,
                self._address,
                brightness_to_percent(int(brightness)),
            )
            return
        await self._hub.async_toggle_dimmer(self._group, self._address)

    async def async_turn_off(self, **kwargs) -> None:
        """Master off sends the same tap pair as on. The module answers."""
        await self._hub.async_toggle_dimmer(self._group, self._address)


def _percent_from_restore(
    last: State | None, extra: ExtraStoredData | None
) -> int | None:
    """Percent stored beside the state, or the brightness of an on lamp."""
    if extra is not None:
        stored = _DimmerLevelStored.from_dict(extra.as_dict())
        if stored is not None:
            return stored.percent
    if last is None or last.state != "on":
        return None
    raw = last.attributes.get(ATTR_BRIGHTNESS)
    if raw is None:
        return None
    try:
        return brightness_to_percent(int(raw))
    except (TypeError, ValueError):
        return None
