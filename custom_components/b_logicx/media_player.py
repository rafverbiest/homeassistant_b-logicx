"""AUD media player virtual module

To understand AUD, it is helpful to think of it as a sort of 'software member'
because there is no real hardware involved. It's normally assigned an address in group 4.
It is being sent commands through DSM media control screens (or using normal INM's)

These commands to the AUD address are monitored by whoever was chosen for
this address. BHS drives a player over Ethernet or RS232 and this card only
shows the command. Home Assistant drives another media player: each of the
eight sources is one source that player reports, and play, stop, volume
steps and mute are passed on to it. That player's source, play, stop, and
mute are also written back as Misc and Select, so the displays follow.
The echo of that write is not passed on again. Volume is not written back.

Classic Set/Reset/Timer/Status do not apply.
Each 'command' consists of two datagrams:

Misc 0.N
Select <group>.<address>.

"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .b_logicx.audio import *
from .const import (
    ADDRESS_TYPE_AUD,
    AUD_CONTROLLER_BHS,
    AUD_CONTROLLER_HA,
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
        controller = str(addr.get("controller") or "").strip().lower()
        if controller not in (AUD_CONTROLLER_BHS, AUD_CONTROLLER_HA):
            _LOGGER.error(
                "AUD %s.%s has no controller; delete that address and add it again",
                group,
                address,
            )
            continue
        target = ""
        stop_action = ""
        mute_action = ""
        volume_step = None
        turn_on_with_play = False
        if controller == AUD_CONTROLLER_HA:
            target = str(addr.get("media_player") or "").strip()
            if not target:
                _LOGGER.error(
                    "AUD %s.%s is controlled by Home Assistant but has no media player",
                    group,
                    address,
                )
                continue
            stop_action = str(addr.get("stop_action") or "")
            mute_action = str(addr.get("mute_action") or "")
            raw_step = addr.get("volume_step")
            if isinstance(raw_step, int) and not isinstance(raw_step, bool):
                volume_step = raw_step
            turn_on_with_play = addr.get("turn_on_with_play") is True
        entities.append(
            BLogicxAudMediaPlayer(
                hub=hub,
                host=host,
                group=group,
                address=address,
                name=str(addr.get("name") or f"Audio {group}.{address}"),
                sources=_source_names(addr),
                target=target,
                stop_action=stop_action,
                mute_action=mute_action,
                volume_step=volume_step,
                turn_on_with_play=turn_on_with_play,
            )
        )
    _LOGGER.info("Creating %d B-Logicx audio entities", len(entities))
    async_add_entities(entities)


class BLogicxAudMediaPlayer(MediaPlayerEntity, RestoreEntity):
    """
    One AUD address presents itself as a Home Assistant media player.

    With a linked player, a bus command is also sent on to that player.
    The echo of our own card is the bus command, so the forward happens once.
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
        target: str = "",
        stop_action: str = "",
        mute_action: str = "",
        volume_step: int | None = None,
        turn_on_with_play: bool = False,
    ) -> None:
        self._hub = hub
        self._host = host
        self._group = group
        self._address = address
        self._sources = sources
        self._target = target
        self._stop_action = stop_action
        self._mute_action = mute_action
        self._volume_step = volume_step
        self._turn_on_with_play = turn_on_with_play
        self._saved_target_volume: float | None = None
        self._player = AudPlayerState()
        self._unsub = None
        self._unsub_target = None
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
            if self._hub.consume_aud_own_echo(cmd.group, cmd.address, cmd.code):
                return
            if self._target and self._target != self.entity_id:
                self.hass.async_create_task(self._forward(cmd.code))

        self._unsub = self._hub.register_aud(self._group, self._address, _on_command)
        last = await self.async_get_last_state()
        if last is not None:
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

        # Restore first. The first mirror then sends only what still differs,
        # instead of treating a blank card as the thing to publish.
        if not self._target:
            return
        self._unsub_target = async_track_state_change_event(
            self.hass, [self._target], self._on_target_state
        )
        current = self.hass.states.get(self._target)
        if current is not None:
            self.hass.async_create_task(self._mirror_state(current))

    @callback
    def _on_target_state(self, event: Event) -> None:
        """The linked player changed. Reflect source, play, stop, and mute."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        self.hass.async_create_task(self._mirror_state(new_state))

    async def _mirror_state(self, state) -> None:
        """Update this card, then send the pairs the displays should show.

        The send is marked, so the echo is not forwarded back to the player.
        """
        source = state.attributes.get("source")
        if source is not None:
            source = str(source)
        muted = state.attributes.get("is_volume_muted")
        if not isinstance(muted, bool):
            muted = None
        codes = mirror_codes(
            self._player,
            state=state.state,
            source=source,
            sources=self._sources,
            muted=muted,
        )
        if not codes:
            return
        for code in codes:
            apply_aud_command(self._player, code)
        self._publish()
        self.async_write_ha_state()
        for code in codes:
            try:
                await self._hub.async_send_aud_own(self._group, self._address, code)
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "AUD %s.%s could not mirror code %s onto the bus",
                    self._group,
                    self._address,
                    code,
                )
                return

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_target:
            self._unsub_target()
            self._unsub_target = None

    @property
    def device_info(self):
        return {
            "identifiers": get_device_identifiers(
                self._host, self._group, self._address
            ),
        }

    async def _forward(self, code: int) -> None:
        """Pass one bus command on to the linked player.

        Stop, mute, and the volume step are the choices stored for this
        address. The linked player's current level is read so a press can
        move that many points. Its features are not read again.
        """
        if not self._target:
            return
        level = None
        player_state = None
        state = self.hass.states.get(self._target)
        if state is not None:
            player_state = state.state
            raw = state.attributes.get("volume_level")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                level = float(raw)
        result = linked_call(
            code,
            self._sources,
            stop_action=self._stop_action or None,
            mute_action=self._mute_action or None,
            volume_step=self._volume_step,
            volume_level=level,
            saved_volume=self._saved_target_volume,
            turn_on_with_play=self._turn_on_with_play,
            player_state=player_state,
        )
        self._saved_target_volume = result.saved_volume
        if result.prelude is not None:
            try:
                await self.hass.services.async_call(
                    "media_player",
                    result.prelude.service,
                    {ATTR_ENTITY_ID: self._target},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "AUD %s.%s could not call %s on %s",
                    self._group,
                    self._address,
                    result.prelude.service,
                    self._target,
                )
        call = result.call
        if call is None:
            return
        data: dict[str, Any] = {ATTR_ENTITY_ID: self._target}
        if call.source is not None:
            data["source"] = call.source
        if call.mute is not None:
            data["is_volume_muted"] = call.mute
        if call.volume_level is not None:
            data["volume_level"] = call.volume_level
        try:
            await self.hass.services.async_call(
                "media_player",
                call.service,
                data,
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "AUD %s.%s could not call %s on %s",
                self._group,
                self._address,
                call.service,
                self._target,
            )

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
