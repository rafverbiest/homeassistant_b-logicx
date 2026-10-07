"""The shutter add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _placeholders


class ShutterSteps:
    """Add or edit screen for one shutter.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_shutter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit one shutter: the open pair, the close pair, and the travel times."""
        if user_input is not None:
            new_cover = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_SHUTTER,
                "open_group": int(user_input["open_group"]),
                "open_address": int(user_input["open_address"]),
                "close_group": int(user_input["close_group"]),
                "close_address": int(user_input["close_address"]),
                "open_time": float(
                    user_input.get("open_time", DEFAULT_OPEN_TIME)
                ),
                "close_time": float(
                    user_input.get("close_time", DEFAULT_CLOSE_TIME)
                ),
                "check_status": user_input.get("check_status", False),
            }
            return await self._commit_address(new_cover)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_shutter",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "open_group", default=defaults.get("open_group", 3)
                    ): int,
                    vol.Required(
                        "open_address",
                        default=defaults.get("open_address", 0),
                    ): int,
                    vol.Required(
                        "close_group", default=defaults.get("close_group", 3)
                    ): int,
                    vol.Required(
                        "close_address",
                        default=defaults.get("close_address", 0),
                    ): int,
                    vol.Required(
                        "open_time",
                        default=float(
                            defaults.get("open_time", DEFAULT_OPEN_TIME)
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=600,
                            step=0.5,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        "close_time",
                        default=float(
                            defaults.get("close_time", DEFAULT_CLOSE_TIME)
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=600,
                            step=0.5,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(),
        )
