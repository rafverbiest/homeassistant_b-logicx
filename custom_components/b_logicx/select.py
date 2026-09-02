"""Select platform for B-Logicx Sfeer (room moods).

One SelectEntity per room. Options are Off plus each configured mood name.
Activating a mood sends Dimmer to that virtual address; the bus answers with
Set/Reset and enforces mutual exclusivity (Reset on the previous mood).
Off sends Dimmer to the currently active mood address.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ADDRESS_TYPE_SFEER,
    COMMAND_DIMMER,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    SFEER_OPTION_OFF,
    get_sfeer_device_identifiers,
    get_sfeer_unique_id,
)
from .hub import BLogicxHub
from .b_logicx.models import BLXEvent

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up B-Logicx Sfeer select entities."""
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    addresses: list[dict] = entry.data.get(CONF_ADDRESSES, [])

    entities: list[BLogicxSfeerSelect] = []
    for addr in addresses:
        if addr.get("type") != ADDRESS_TYPE_SFEER:
            continue
        moods = addr.get("moods") or []
        if not moods:
            _LOGGER.debug(
                "Sfeer room %r has no moods yet (Off only until moods are added)",
                addr.get("name"),
            )
        try:
            entities.append(
                BLogicxSfeerSelect(
                    hub=hub,
                    host=host,
                    room_name=addr.get("name", "Sfeer"),
                    moods=moods,
                    check_status=addr.get("check_status", False),
                    room_group=addr.get("group"),
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Skipping invalid Sfeer entry %s: %s", addr, err)

    _LOGGER.info(
        "Creating %d B-Logicx Sfeer select entities: %s",
        len(entities),
        ", ".join(e.name for e in entities) or "(none)",
    )
    async_add_entities(entities)


class BLogicxSfeerSelect(SelectEntity):
    """One Select per Sfeer room: Off + mood names."""

    _attr_should_poll = False

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        room_name: str,
        moods: list[dict],
        check_status: bool = False,
        room_group: int | None = None,
    ) -> None:
        self._hub = hub
        self._host = host
        self._room_name = room_name
        self._check_status = check_status
        self._room_group = room_group

        # mood name -> (group, address)
        self._mood_map: dict[str, tuple[int, int]] = {}
        # (group, address) -> mood name
        self._addr_map: dict[tuple[int, int], str] = {}
        for m in moods:
            mname = str(m["name"]).strip()
            g, a = int(m["group"]), int(m["address"])
            if not mname:
                continue
            if mname in self._mood_map:
                _LOGGER.warning(
                    "Sfeer room %r: duplicate mood name %r ignored",
                    room_name,
                    mname,
                )
                continue
            self._mood_map[mname] = (g, a)
            self._addr_map[(g, a)] = mname

        # Empty moods allowed (room created before moods); options = Off only
        self._attr_name = room_name
        self._attr_unique_id = get_sfeer_unique_id(host, room_name)
        self._attr_options = [SFEER_OPTION_OFF] + list(self._mood_map.keys())
        self._attr_current_option: str | None = SFEER_OPTION_OFF

        self._unsubs: list[Callable[[], None]] = []

    @property
    def device_info(self):
        return {
            "identifiers": get_sfeer_device_identifiers(
                self._host, self._room_name
            ),
            "name": self._room_name,
            "manufacturer": "B-Logicx",
            "model": "Sfeer (room moods)",
        }

    async def async_added_to_hass(self) -> None:
        for (g, a), _mname in self._addr_map.items():
            self._unsubs.append(
                self._hub.register_listener(self._handle_event, g, a)
            )

        if self._check_status:
            await self._query_status()

    async def async_will_remove_from_hass(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _query_status(self) -> None:
        """Serial Status on each mood; first Set wins as active."""
        active: str | None = None
        for mname, (g, a) in self._mood_map.items():
            is_on = await self._hub.async_request_status(g, a)
            if is_on is True:
                if active is not None:
                    _LOGGER.warning(
                        "Sfeer %r: multiple moods active on Status "
                        "(%s and %s); using first",
                        self._room_name,
                        active,
                        mname,
                    )
                else:
                    active = mname
        self._attr_current_option = active if active else SFEER_OPTION_OFF
        _LOGGER.debug(
            "Sfeer %r: Status snapshot → %s",
            self._room_name,
            self._attr_current_option,
        )
        self.async_write_ha_state()

    @callback
    def _handle_event(self, event: BLXEvent) -> None:
        key = (event.group, event.address)
        mname = self._addr_map.get(key)
        if mname is None:
            return
        if event.command == "Set":
            self._attr_current_option = mname
            self.async_write_ha_state()
        elif event.command == "Reset":
            if self._attr_current_option == mname:
                self._attr_current_option = SFEER_OPTION_OFF
                self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Activate a mood or turn Off the active one (Dimmer)."""
        if option not in self._attr_options:
            _LOGGER.warning(
                "Sfeer %r: unknown option %r", self._room_name, option
            )
            return

        if option == SFEER_OPTION_OFF:
            current = self._attr_current_option
            if current is None or current == SFEER_OPTION_OFF:
                return
            ga = self._mood_map.get(current)
            if ga is None:
                self._attr_current_option = SFEER_OPTION_OFF
                self.async_write_ha_state()
                return
            g, a = ga
            await self._hub.async_send(COMMAND_DIMMER, g, a)
            # Optimistic; bus Reset confirms
            self._attr_current_option = SFEER_OPTION_OFF
            self.async_write_ha_state()
            return

        ga = self._mood_map.get(option)
        if ga is None:
            return
        g, a = ga
        await self._hub.async_send(COMMAND_DIMMER, g, a)
        # Optimistic; bus Set confirms (and Reset on previous mood)
        self._attr_current_option = option
        self.async_write_ha_state()
