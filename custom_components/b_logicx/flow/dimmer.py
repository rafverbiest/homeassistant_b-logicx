"""The dimmer add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _placeholders


class DimmerSteps:
    """Add or edit screen for one dimmer.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_dimmer(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a dimmer. Name, group, address, and the two module options."""
        if user_input is not None:
            new_addr: dict[str, Any] = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_DIMMER,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "remembers_level": bool(user_input.get("remembers_level", False)),
                "participates_in_moods": bool(
                    user_input.get("participates_in_moods", True)
                ),
                "check_status": bool(user_input.get("check_status", False)),
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_dimmer",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required("group", default=defaults.get("group", 5)): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Optional(
                        "remembers_level",
                        default=defaults.get("remembers_level", False),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "participates_in_moods",
                        default=defaults.get("participates_in_moods", True),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(),
        )
