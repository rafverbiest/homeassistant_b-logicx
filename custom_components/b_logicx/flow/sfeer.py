"""Sfeer room and mood screens. Edit opens the room screen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..address_config import entries_sorted_for_picker
from ..const import *
from .common import (
    _entry_key,
    _entry_label,
    _find_entry,
    _flow_lang,
    _placeholders,
    _upsert_by_key,
)


class SfeerSteps:
    """Add or edit a Sfeer room, and add a mood inside one.

    Mixed into BLogicxOptionsFlow, which saves through _save_and_reload.
    A mood reads the room chosen on the previous step.
    """

    async def async_step_add_sfeer_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create or edit a Sfeer room (one bus group; moods added separately)."""
        current = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        defaults = getattr(self, "_edit_defaults", {}) or {}
        editing = bool(getattr(self, "_edit_key", None))

        if user_input is not None:
            room_name = user_input["room_name"].strip()
            room_group = int(user_input["group"])
            check = user_input.get("check_status", False)
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                old = _find_entry(current, edit_key) or {}
                moods = list(old.get("moods") or [])
                # Keep moods, rewrite their group if room group changed
                moods = [
                    {
                        "name": m["name"],
                        "group": room_group,
                        "address": int(m["address"]),
                    }
                    for m in moods
                ]
                self._edit_key = None
                self._edit_defaults = None
                current = [a for a in current if _entry_key(a) != edit_key]
            else:
                moods = []
            new_room = {
                "name": room_name,
                "type": ADDRESS_TYPE_SFEER,
                "group": room_group,
                "moods": moods,
                "check_status": check,
            }
            current = _upsert_by_key(current, new_room)
            await self._save_and_reload(current)
            return self._finish_options()

        used = {
            sfeer_room_group(a)
            for a in current
            if a.get("type") == ADDRESS_TYPE_SFEER
            and (
                not editing
                or _entry_key(a) != getattr(self, "_edit_key", None)
            )
        }
        if editing and defaults:
            def_group = sfeer_room_group(defaults)
            def_name = defaults.get("name", "")
            def_check = defaults.get("check_status", False)
            moods = defaults.get("moods") or []
            mood_desc = (
                ", ".join(f"{m.get('name')} → {m.get('address')}" for m in moods)
                or (
                    "(nog geen — gebruik Sfeer toevoegen)"
                    if _flow_lang(self.hass) == "nl"
                    else "(none yet — use Add Sfeer)"
                )
            )
        else:
            def_group = next_sfeer_group(used)
            def_name = ""
            def_check = False
            mood_desc = (
                "(nog geen — gebruik Sfeer toevoegen na het aanmaken van de ruimte)"
                if _flow_lang(self.hass) == "nl"
                else "(none yet — use Add Sfeer after creating the room)"
            )
            self._edit_defaults = None

        return self.async_show_form(
            step_id="add_sfeer_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room_name", default=def_name): str,
                    vol.Required("group", default=def_group): int,
                    vol.Optional(
                        "check_status", default=def_check
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(moods=mood_desc),
        )

    async def async_step_add_sfeer_mood(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: pick Sfeer room (group is shown in the label)."""
        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        rooms = [a for a in current if a.get("type") == ADDRESS_TYPE_SFEER]
        if not rooms:
            return await self.async_step_init()

        if user_input is not None:
            self._sfeer_mood_room_key = user_input["room"]
            return await self.async_step_add_sfeer_mood_details()

        room_options = [
            selector.SelectOptionDict(
                value=_entry_key(r),
                label=_entry_label(r),
            )
            for r in entries_sorted_for_picker(rooms)
        ]
        return self.async_show_form(
            step_id="add_sfeer_mood",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=room_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(),
        )

    async def async_step_add_sfeer_mood_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: mood name + address; group fixed to the room's group."""
        current = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        room_key = getattr(self, "_sfeer_mood_room_key", None)
        room = _find_entry(current, room_key) if room_key else None
        if not room or room.get("type") != ADDRESS_TYPE_SFEER:
            return await self.async_step_add_sfeer_mood()

        room_group = sfeer_room_group(room)
        moods = list(room.get("moods") or [])
        if moods:
            def_addr = max(int(m.get("address", 0)) for m in moods) + 1
        else:
            def_addr = DEFAULT_SFEER_ADDRESS

        if user_input is not None:
            moods.append(
                {
                    "name": user_input["mood_name"].strip(),
                    "group": room_group,
                    "address": int(user_input["address"]),
                }
            )
            new_room = {
                "name": room["name"],
                "type": ADDRESS_TYPE_SFEER,
                "group": room_group,
                "moods": moods,
                "check_status": room.get("check_status", False),
            }
            addresses = [a for a in current if _entry_key(a) != room_key]
            addresses = _upsert_by_key(addresses, new_room)
            self._sfeer_mood_room_key = None
            await self._save_and_reload(addresses)
            return self._finish_options()

        return self.async_show_form(
            step_id="add_sfeer_mood_details",
            data_schema=vol.Schema(
                {
                    vol.Required("mood_name"): str,
                    vol.Required("address", default=def_addr): int,
                }
            ),
            description_placeholders=_placeholders(room_name=str(room.get("name", "")),
                group=str(room_group),
            ),
        )
