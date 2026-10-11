"""The BL-AUD add and edit screens.

The first screen asks whether BHS or Home Assistant acts on this address.
BHS then asks for eight source names, as before. Home Assistant asks for a
media player, then for one of that player's sources in each of the eight slots.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from ..b_logicx.audio import (
    DEFAULT_VOLUME_STEP,
    MUTE_ACTIONS,
    STOP_ACTIONS,
    VOLUME_STEP_MAX,
    VOLUME_STEP_MIN,
    aud_link_options,
    can_set_volume,
    can_turn_on,
    keep_or_default,
    mute_choices,
    stop_choices,
    supported_feature_mask,
)
from ..const import *
from .common import _flow_lang, _placeholders


def _stored_volume_step(raw: object) -> int | None:
    """A saved volume step, or None when this address has none."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if isinstance(raw, float) and not raw.is_integer():
        return None
    step = int(raw)
    if step < VOLUME_STEP_MIN or step > VOLUME_STEP_MAX:
        return None
    return step


class AudSteps:
    """Add or edit screens for one BL-AUD.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address.
    """

    def _aud_begin(self) -> dict[str, Any]:
        """Defaults for this add or edit. Kept for the later screens."""
        draft = getattr(self, "_aud_draft", None)
        if draft:
            return draft
        defaults = self._take_edit_defaults()
        stored = defaults.get("controller")
        if stored in (AUD_CONTROLLER_BHS, AUD_CONTROLLER_HA):
            controller = stored
        elif defaults:
            # A saved address without this field is not BHS. The form asks.
            controller = None
        else:
            controller = AUD_CONTROLLER_BHS
        self._aud_draft = {
            "name": defaults.get("name", "Audio"),
            "group": int(defaults.get("group", DEFAULT_AUD_GROUP)),
            "address": int(defaults.get("address", 1)),
            "controller": controller,
            "media_player": defaults.get("media_player", ""),
            # The player this address was saved with. Later screens compare
            # against it, so choosing a different player cannot reuse these names.
            "_saved_player": str(defaults.get("media_player") or "").strip(),
            "stop_action": str(defaults.get("stop_action") or ""),
            "mute_action": str(defaults.get("mute_action") or ""),
            "volume_step": _stored_volume_step(defaults.get("volume_step")),
            "turn_on_with_play": defaults.get("turn_on_with_play")
            if isinstance(defaults.get("turn_on_with_play"), bool)
            else None,
        }
        for i in range(1, 9):
            key = f"source_{i}"
            self._aud_draft[key] = defaults.get(key) or ""
        return self._aud_draft

    def _aud_exclude_players(self) -> list[str]:
        """BL-AUD entities of this entry, so a player is not linked to itself."""
        registry = er.async_get(self.hass)
        return [
            entry.entity_id
            for entry in er.async_entries_for_config_entry(
                registry, self.config_entry.entry_id
            )
            if entry.domain == "media_player"
        ]

    def _reported_features(self, entity_id: str) -> int:
        """Feature bits the linked player is reporting right now."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return 0
        return supported_feature_mask(state.attributes.get("supported_features"))

    def _apply_player_features(
        self,
        draft: dict[str, Any],
        entity_id: str,
        sources: list[str],
        features: int,
    ) -> None:
        """Store the commands this player can perform."""
        stops = stop_choices(features)
        mutes = mute_choices(features)
        draft["media_player"] = entity_id
        draft["_link_sources"] = sources
        draft["_features_known"] = True
        draft["_stop_choices"] = stops
        draft["_mute_choices"] = mutes
        draft["_can_set_volume"] = can_set_volume(features)
        draft["stop_action"] = keep_or_default(draft.get("stop_action"), stops) or ""
        draft["mute_action"] = keep_or_default(draft.get("mute_action"), mutes) or ""
        if draft["_can_set_volume"]:
            if draft.get("volume_step") is None:
                draft["volume_step"] = DEFAULT_VOLUME_STEP
        else:
            draft["volume_step"] = None
        draft["_can_turn_on"] = can_turn_on(features)
        if draft["_can_turn_on"]:
            if not isinstance(draft.get("turn_on_with_play"), bool):
                draft["turn_on_with_play"] = True
        else:
            draft["turn_on_with_play"] = None

    def _keep_saved_actions(self, draft: dict[str, Any], entity_id: str, sources: list[str]) -> None:
        """The player is quiet. Keep the commands already stored for it."""
        draft["media_player"] = entity_id
        draft["_link_sources"] = sources
        draft["_features_known"] = False
        draft["_can_set_volume"] = draft.get("volume_step") is not None
        draft["_stop_choices"] = (
            [draft["stop_action"]] if draft.get("stop_action") in STOP_ACTIONS else []
        )
        draft["_mute_choices"] = (
            [draft["mute_action"]] if draft.get("mute_action") in MUTE_ACTIONS else []
        )
        draft["_can_turn_on"] = isinstance(draft.get("turn_on_with_play"), bool)

    def _reported_sources(self, entity_id: str) -> list[str]:
        """Sources the linked player is reporting right now."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return []
        raw = state.attributes.get("source_list") or []
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for item in raw:
            label = str(item).strip()
            if label and label not in names:
                names.append(label)
        return names

    def _aud_player_known(self, entity_id: str) -> bool:
        """True when this entity is in the state machine or the registry."""
        if self.hass.states.get(entity_id) is not None:
            return True
        return er.async_get(self.hass).async_get(entity_id) is not None

    def _aud_saved_sources(self, draft: dict[str, Any]) -> list[str]:
        return [str(draft.get(f"source_{i}") or "") for i in range(1, 9)]

    def _aud_choice(self, draft: dict[str, Any], entity_id: str) -> list[str] | None:
        """Dropdown options for this player, or None when the list is empty."""
        return aud_link_options(
            self._reported_sources(entity_id),
            self._aud_saved_sources(draft),
            same_player=entity_id == str(draft.get("_saved_player") or "").strip(),
        )

    async def async_step_add_aud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Name, address, and whether BHS or Home Assistant acts on it."""
        # A new visit starts clean. The options flow keeps this object, so a
        # draft from an abandoned edit must not fill the next address.
        if user_input is None:
            self._aud_draft = None
        draft = self._aud_begin()
        if user_input is not None:
            draft["name"] = user_input["name"].strip() or "Audio"
            draft["group"] = int(user_input["group"])
            draft["address"] = int(user_input["address"])
            draft["controller"] = user_input["controller"]
            if draft["controller"] == AUD_CONTROLLER_HA:
                return await self.async_step_add_aud_player()
            return await self.async_step_add_aud_sources()

        return self.async_show_form(
            step_id="add_aud",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=draft["name"]): str,
                    vol.Required("group", default=draft["group"]): int,
                    vol.Required("address", default=draft["address"]): int,
                    (
                        vol.Required("controller", default=draft["controller"])
                        if draft["controller"]
                        in (AUD_CONTROLLER_BHS, AUD_CONTROLLER_HA)
                        else vol.Required("controller")
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[AUD_CONTROLLER_BHS, AUD_CONTROLLER_HA],
                            translation_key="aud_controller",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(),
        )

    async def async_step_add_aud_player(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """The media player Home Assistant will control."""
        draft = self._aud_begin()
        errors: dict[str, str] = {}
        chosen = ""
        if user_input is not None:
            chosen = str(user_input["media_player"]).strip()
            live = self._reported_sources(chosen)
            if live:
                features = self._reported_features(chosen)
                if not stop_choices(features):
                    errors["media_player"] = "aud_no_stop"
                else:
                    self._apply_player_features(draft, chosen, live, features)
                    return await self.async_step_add_aud_links()
            else:
                saved = self._aud_choice(draft, chosen)
                if saved is None:
                    errors["media_player"] = "aud_no_sources"
                elif draft.get("stop_action") not in STOP_ACTIONS:
                    errors["media_player"] = "aud_no_features"
                else:
                    self._keep_saved_actions(draft, chosen, saved)
                    return await self.async_step_add_aud_links()

        show = chosen or str(draft.get("media_player") or "").strip()
        player_field: Any = vol.Required("media_player")
        if show and (chosen or self._aud_player_known(show)):
            player_field = vol.Required("media_player", default=show)
        return self.async_show_form(
            step_id="add_aud_player",
            data_schema=vol.Schema(
                {
                    player_field: selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player",
                            exclude_entities=self._aud_exclude_players(),
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=_placeholders(),
        )

    async def async_step_add_aud_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Eight source names. BHS keeps control of the real player."""
        draft = self._aud_begin()
        if user_input is not None:
            sources = {
                f"source_{i}": str(user_input.get(f"source_{i}") or "").strip()
                or f"Source {i}"
                for i in range(1, 9)
            }
            return await self._aud_commit(sources)

        schema: dict[Any, Any] = {}
        for i in range(1, 9):
            key = f"source_{i}"
            schema[vol.Optional(key, default=draft.get(key) or f"Source {i}")] = str
        return self.async_show_form(
            step_id="add_aud_sources",
            data_schema=vol.Schema(schema),
            description_placeholders=_placeholders(),
        )

    async def async_step_add_aud_links(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """One dropdown per BL-DSM source, filled from the linked player."""
        draft = self._aud_begin()
        options: list[str] = list(draft.get("_link_sources") or [])
        if user_input is not None:
            sources = {
                f"source_{i}": str(user_input[f"source_{i}"]).strip()
                for i in range(1, 9)
            }
            if user_input.get("stop_action") in STOP_ACTIONS:
                draft["stop_action"] = user_input["stop_action"]
            if user_input.get("mute_action") in MUTE_ACTIONS:
                draft["mute_action"] = user_input["mute_action"]
            elif not draft.get("_mute_choices"):
                draft["mute_action"] = ""
            if "volume_step" in user_input:
                draft["volume_step"] = _stored_volume_step(user_input["volume_step"])
            elif not draft.get("_can_set_volume"):
                draft["volume_step"] = None
            if "turn_on_with_play" in user_input:
                draft["turn_on_with_play"] = bool(user_input["turn_on_with_play"])
            elif not draft.get("_can_turn_on"):
                draft["turn_on_with_play"] = None
            return await self._aud_commit(sources)

        if not options:
            found = self._aud_choice(
                draft, str(draft.get("media_player") or "").strip()
            )
            options = list(found or [])
        if not options:
            return await self.async_step_add_aud_player()

        schema: dict[Any, Any] = {}
        stop_opts = list(draft.get("_stop_choices") or [])
        if stop_opts:
            current_stop = draft.get("stop_action")
            schema[vol.Required(
                "stop_action",
                default=current_stop if current_stop in stop_opts else stop_opts[0],
            )] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=stop_opts,
                    translation_key="aud_stop_action",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        mute_opts = list(draft.get("_mute_choices") or [])
        if mute_opts:
            current_mute = draft.get("mute_action")
            schema[vol.Required(
                "mute_action",
                default=current_mute if current_mute in mute_opts else mute_opts[0],
            )] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=mute_opts,
                    translation_key="aud_mute_action",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        if draft.get("_can_turn_on"):
            schema[vol.Required(
                "turn_on_with_play",
                default=draft.get("turn_on_with_play") is not False,
            )] = selector.BooleanSelector()
        if draft.get("_can_set_volume"):
            step = draft.get("volume_step")
            if step is None:
                step = DEFAULT_VOLUME_STEP
            schema[vol.Required("volume_step", default=int(step))] = (
                selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=VOLUME_STEP_MIN,
                        max=VOLUME_STEP_MAX,
                        step=1,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            )
        for i in range(1, 9):
            key = f"source_{i}"
            current = str(draft.get(key) or "")
            default = current if current in options else options[0]
            schema[
                vol.Required(key, default=default)
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        mute_missing = bool(draft.get("_features_known")) and not draft.get(
            "_mute_choices"
        )
        if mute_missing and _flow_lang(self.hass) == "nl":
            mute_note = (
                "Deze speler kan niet dempen en kan het volume niet zetten, "
                "dus dempen wordt niet doorgegeven."
            )
        elif mute_missing:
            mute_note = (
                "This player cannot mute and cannot set volume, "
                "so mute is not passed on."
            )
        else:
            mute_note = ""
        return self.async_show_form(
            step_id="add_aud_links",
            data_schema=vol.Schema(schema),
            description_placeholders=_placeholders(mute_note=mute_note),
        )

    async def _aud_commit(self, sources: dict[str, str]) -> FlowResult:
        draft = self._aud_draft
        new_addr: dict[str, Any] = {
            "name": draft["name"],
            "type": ADDRESS_TYPE_AUD,
            "group": int(draft["group"]),
            "address": int(draft["address"]),
            "controller": draft["controller"],
        }
        if draft["controller"] == AUD_CONTROLLER_HA:
            new_addr["media_player"] = draft["media_player"]
            if draft.get("stop_action") in STOP_ACTIONS:
                new_addr["stop_action"] = draft["stop_action"]
            if draft.get("mute_action") in MUTE_ACTIONS:
                new_addr["mute_action"] = draft["mute_action"]
            step = _stored_volume_step(draft.get("volume_step"))
            if step is not None and (
                draft.get("_can_set_volume") or not draft.get("_features_known")
            ):
                new_addr["volume_step"] = step
            if isinstance(draft.get("turn_on_with_play"), bool) and (
                draft.get("_can_turn_on") or not draft.get("_features_known")
            ):
                new_addr["turn_on_with_play"] = draft["turn_on_with_play"]
        new_addr.update(sources)
        self._aud_draft = None
        return await self._commit_address(new_addr)
