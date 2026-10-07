"""The BL-AUD add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult

from ..const import *
from .common import _placeholders


class AudSteps:
    """Add or edit screen for one BL-AUD.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_aud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a BL-AUD. Group defaults to 4. Empty sources become Source N."""
        if user_input is not None:
            new_addr: dict[str, Any] = {
                "name": user_input["name"].strip() or "Audio",
                "type": ADDRESS_TYPE_AUD,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
            }
            for i in range(1, 9):
                key = f"source_{i}"
                label = str(user_input.get(key) or "").strip()
                new_addr[key] = label or f"Source {i}"
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        schema: dict[Any, Any] = {
            vol.Required("name", default=defaults.get("name", "Audio")): str,
            vol.Required(
                "group",
                default=int(defaults.get("group", DEFAULT_AUD_GROUP)),
            ): int,
            vol.Required(
                "address", default=int(defaults.get("address", 1))
            ): int,
        }
        for i in range(1, 9):
            key = f"source_{i}"
            schema[
                vol.Optional(key, default=defaults.get(key) or f"Source {i}")
            ] = str
        return self.async_show_form(
            step_id="add_aud",
            data_schema=vol.Schema(schema),
            description_placeholders=_placeholders(),
        )
