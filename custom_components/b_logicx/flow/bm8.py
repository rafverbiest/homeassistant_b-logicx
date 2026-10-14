"""The BM8 add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult

from ..const import *
from .common import _placeholders


class Bm8Steps:
    """Add or edit screen for one doorbell chime.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_bm8(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a BM8. A press on one of its buttons is the whole action."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Chime",
                "type": ADDRESS_TYPE_BM8,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_bm8",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Chime")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_BM8_GROUP)),
                    ): int,
                    vol.Required(
                        "address", default=int(defaults.get("address", 0))
                    ): int,
                }
            ),
            description_placeholders=_placeholders(),
        )
