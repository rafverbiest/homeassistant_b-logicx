"""The SoftM add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _placeholders


class SoftmSteps:
    """Add or edit screen for one SoftM.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_softm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a SoftM. Set/Reset only; VSM tracking is optional."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Absent means the box was cleared. The form default is on.
            vsm = bool(user_input.get("enable_softm_status_tracking", False))
            timer = user_input.get("softm_timer")
            timer_val: float | None = None
            if timer not in (None, "", 0, 0.0):
                timer_val = float(timer)
                if timer_val <= 0:
                    timer_val = None
            if timer_val and not vsm:
                errors["base"] = "softm_timer_needs_vsm"
            else:
                new_addr: dict[str, Any] = {
                    "name": user_input["name"].strip(),
                    "type": ADDRESS_TYPE_SOFTM,
                    "group": int(user_input["group"]),
                    "address": int(user_input["address"]),
                    "on_command": DEFAULT_ON_COMMAND,
                    "off_command": DEFAULT_OFF_COMMAND,
                    "check_status": False,
                    "enable_softm_status_tracking": vsm,
                    "persist_state": bool(user_input.get("persist_state", True)),
                    "default_state": bool(user_input.get("default_state", False)),
                }
                if timer_val:
                    new_addr["softm_timer"] = timer_val
                return await self._commit_address(new_addr)

        defaults = (
            user_input
            if user_input is not None
            else self._take_edit_defaults()
        )
        return self.async_show_form(
            step_id="add_softm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "group", default=defaults.get("group", 10)
                    ): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Optional(
                        "enable_softm_status_tracking",
                        default=defaults.get("enable_softm_status_tracking", True),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "softm_timer",
                        default=defaults.get("softm_timer", 0) or 0,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=86400,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "persist_state",
                        default=defaults.get("persist_state", True),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "default_state",
                        default=defaults.get("default_state", False),
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders=_placeholders(),
        )
