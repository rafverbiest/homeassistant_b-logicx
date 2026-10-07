"""BL-AUD media player virtual module

To understand BL-AUD, it is helpful to think of it as a sort of 'software member'
because there is no real hardware involved. It's normally assigned an address in group 4.
It is being sent commands through BL-DSM media control screens (or using normal INM's)

These commands to the BL-AUD address are monitored by BL-BHS, which takes action
controlling a physical media player, usually connected to the BHS via Ethernet or RS232.

This is an implementation that mimics these commands and also catches them
so we can display media player status.

In future versions, it would be nice to try to bypass BHS and
control media players directly from Home Assistant.

Classic Set/Reset/Timer/Status do not apply.
Each 'command' consists of two datagrams:

Misc 0.N
Select <group>.<address>.

"""

from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .b_logicx.audio import *
from .const import (
    ADDRESS_TYPE_AUD,
    CONF_ADDRESSES,
    CONF_HOST,
    DOMAIN,
    get_device_identifiers,
    get_entity_unique_id,
)
from .hub import BLogicxHub

_LOGGER = logging.getLogger(__name__)

_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
)


def _source_names(addr: dict) -> list[str]:
    names: list[str] = []
    for i in range(1, 9):
        label = str(addr.get(f"source_{i}") or "").strip()
        names.append(label or f"Source {i}")
    return names


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    entities: list[BLogicxAudMediaPlayer] = []
    for addr in entry.data.get(CONF_ADDRESSES, []):
        if addr.get("type") != ADDRESS_TYPE_AUD:
            continue
        if "group" not in addr or "address" not in addr:
            continue
        group = int(addr["group"])
        address = int(addr["address"])
        entities.append(
            BLogicxAudMediaPlayer(
                hub=hub,
                host=host,
                group=group,
                address=address,
                name=str(addr.get("name") or f"Audio {group}.{address}"),
                sources=_source_names(addr),
            )
        )
    _LOGGER.info("Creating %d B-Logicx audio entities", len(entities))
    async_add_entities(entities)


class BLogicxAudMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """
    One BL-AUD address presents itself as a Home Assistant media player.
    I'm still contemplating how to cleanly make it work in future when HA needs
    to also control the media player trough other integrations
    """

    _attr_should_poll = False
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = _FEATURES

    def __init__(
        self,
        hub: BLogicxHub,
        host: str,
        group: int,
        address: int,
        name: str,
        sources: list[str],
    ) -> None:
        self._hub = hub
        self._host = host
        self._group = group
        self._address = address
        self._sources = sources
        self._player = AudPlayerState()
        self._unsub = None
        self._attr_name = name
        self._attr_unique_id = get_entity_unique_id(host, group, address)
        self._attr_source_list = list(sources)
        self._attr_source = None
        self._attr_media_title = None
        self._attr_state = None
        self._attr_is_volume_muted = False

    def _publish(self) -> None:
        if self._player.state == "playing":
            self._attr_state = MediaPlayerState.PLAYING
        elif self._player.state == "idle":
            self._attr_state = MediaPlayerState.IDLE
        title = None
        if self._player.source_index is not None:
            idx = self._player.source_index - 1
            if 0 <= idx < len(self._sources):
                title = self._sources[idx]
        # The bus has no track name, so we're showing the source name
        # in the media player widget. Not how it's supposed to work
        # but better than an empty widget
        self._attr_source = title
        self._attr_media_title = title
        self._attr_is_volume_muted = self._player.muted

    async def _send(self, code: int) -> None:
        """Send Misc then Select, and apply that code locally.

        The echo of those frames comes back through the hub and applies again.
        Both applies produce the same player state.
        """
        await self._hub.async_send_aud(self._group, self._address, code)
        apply_aud_command(self._player, code)
        self._publish()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_command(cmd: AudCommand) -> None:
            apply_aud_command(self._player, cmd.code)
            self._publish()
            self.async_write_ha_state()

        self._unsub = self._hub.register_aud(self._group, self._address, _on_command)

        last = await self.async_get_last_state()
        if last is None:
            return
        if last.state in (MediaPlayerState.PLAYING, "playing"):
            self._player.state = "playing"
        elif last.state in (MediaPlayerState.IDLE, "idle"):
            self._player.state = "idle"
        source = last.attributes.get("source")
        if source in self._sources:
            self._player.source_index = self._sources.index(source) + 1
        muted = last.attributes.get("is_volume_muted")
        if isinstance(muted, bool):
            self._player.muted = muted
        self._publish()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self):
        return {
            "identifiers": get_device_identifiers(
                self._host, self._group, self._address
            ),
        }

    async def async_media_play(self) -> None:
        await self._send(AUD_PLAY)

    async def async_media_stop(self) -> None:
        await self._send(AUD_STOP)

    async def async_select_source(self, source: str) -> None:
        if source not in self._sources:
            return
        code = self._sources.index(source) + 1
        if not AUD_SOURCE_MIN <= code <= AUD_SOURCE_MAX:
            return
        await self._send(code)

    async def async_volume_up(self) -> None:
        await self._send(AUD_VOLUME_UP)

    async def async_volume_down(self) -> None:
        await self._send(AUD_VOLUME_DOWN)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send(AUD_MUTE_ON if mute else AUD_MUTE_OFF)
