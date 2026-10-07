"""The RTC add and edit screen. Edit opens this same step."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..const import *
from .common import _placeholders


class RtcSteps:
    """Add or edit screen for one bus clock.

    Mixed into BLogicxOptionsFlow, which saves through _commit_address
    and fills the form from _take_edit_defaults.
    """

    async def async_step_add_rtc(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a clock: sync interval, the minute past the hour, and daylight saving."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Bus clock",
                "type": ADDRESS_TYPE_RTC,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "sync_interval_hours": float(
                    user_input.get(
                        "sync_interval_hours", DEFAULT_RTC_SYNC_INTERVAL_HOURS
                    )
                ),
                "sync_minute": int(
                    user_input.get("sync_minute", DEFAULT_RTC_SYNC_MINUTE)
                ),
                "sync_on_startup": user_input.get(
                    "sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP
                ),
                "sync_on_dst": user_input.get(
                    "sync_on_dst", DEFAULT_RTC_SYNC_ON_DST
                ),
                "dst_delay_minutes": int(
                    user_input.get(
                        "dst_delay_minutes", DEFAULT_RTC_DST_DELAY_MINUTES
                    )
                ),
                "check_status": False,
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_rtc",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Bus clock")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_RTC_GROUP)),
                    ): int,
                    vol.Required(
                        "address",
                        default=int(defaults.get("address", 1)),
                    ): int,
                    vol.Required(
                        "sync_interval_hours",
                        default=float(
                            defaults.get(
                                "sync_interval_hours",
                                DEFAULT_RTC_SYNC_INTERVAL_HOURS,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=168,
                            step=1,
                            unit_of_measurement="h",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        "sync_minute",
                        default=int(
                            defaults.get(
                                "sync_minute", DEFAULT_RTC_SYNC_MINUTE
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=59,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "sync_on_startup",
                        default=bool(
                            defaults.get(
                                "sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP
                            )
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "sync_on_dst",
                        default=bool(
                            defaults.get("sync_on_dst", DEFAULT_RTC_SYNC_ON_DST)
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "dst_delay_minutes",
                        default=int(
                            defaults.get(
                                "dst_delay_minutes",
                                DEFAULT_RTC_DST_DELAY_MINUTES,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=60,
                            step=1,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(),
        )
