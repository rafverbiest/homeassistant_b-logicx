"""One light per dimmer: master on/off, and a slider for the percent.

Set and Reset are the master switch. The slider sends Data 0.<percent>
and then Timer to this dimmer. A Sfeer in the group clears the known
percent; the dimmer's own Set or Reset updates on or off.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .b_logicx.dimmer import (
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
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid dimmer entry %s: %s", addr, err)

    _LOGGER.info("Creating %d B-Logicx dimmer light(s)", len(entities))
    async_add_entities(entities)


class BLogicxDimmer(LightEntity):
    """A dimmer. Level and on/off start unknown and are not restored."""

    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        config: DimmerConfig,
        name: str,
    ) -> None:
        self._hub = hub
        self._host = host
        self._config = config
        self._group = config.group
        self._address = config.address
        self._attr_name = name
        self._attr_unique_id = get_dimmer_unique_id(host, config.group, config.address)
        self._attr_is_on = None
        self._attr_brightness = None
        self._attr_color_mode = None
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Listen for bus updates. Do not restore a level from the last run."""
        self._unsub = self._hub.register_dimmer(self._config, self._handle_view)
        self._show(self._hub.dimmer_view(self._group, self._address))

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
        """Slider movement sends a percent. A plain on sends Set."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            await self._hub.async_set_dimmer_level(
                self._group,
                self._address,
                brightness_to_percent(int(brightness)),
            )
            return
        await self._hub.async_set_dimmer_on(self._group, self._address, True)

    async def async_turn_off(self, **kwargs) -> None:
        """Master off is Reset."""
        await self._hub.async_set_dimmer_on(self._group, self._address, False)
