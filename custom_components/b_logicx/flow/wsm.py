"""The BL-WSM add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _placeholders


class WsmSteps:
    """Add or edit screen for one wind sensor.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_wsm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a wind sensor. check_status asks for a reading at startup."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Wind sensor",
                "type": ADDRESS_TYPE_WSM,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "check_status": user_input.get("check_status", False),
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_wsm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Wind sensor")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_WSM_GROUP)),
                    ): int,
                    vol.Required(
                        "address", default=int(defaults.get("address", 0))
                    ): int,
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(),
        )
