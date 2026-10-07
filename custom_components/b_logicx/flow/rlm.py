"""The RLM add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _command_selector, _placeholders


class RlmSteps:
    """Add or edit screen for one RLM switch.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_rlm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit an RLM switch. SoftM has its own screen."""
        if user_input is not None:
            new_addr: dict[str, Any] = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_RLM,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "on_command": user_input.get("on_command", DEFAULT_ON_COMMAND),
                "off_command": user_input.get("off_command", DEFAULT_OFF_COMMAND),
                "check_status": bool(user_input.get("check_status", False)),
                "enable_softm_status_tracking": False,
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_rlm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required("group", default=defaults.get("group", 2)): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Required(
                        "on_command",
                        default=defaults.get("on_command", DEFAULT_ON_COMMAND),
                    ): _command_selector(ON_COMMANDS, DEFAULT_ON_COMMAND),
                    vol.Required(
                        "off_command",
                        default=defaults.get("off_command", DEFAULT_OFF_COMMAND),
                    ): _command_selector(OFF_COMMANDS, DEFAULT_OFF_COMMAND),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(),
        )
