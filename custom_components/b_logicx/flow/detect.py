"""Detect one unknown Set or Reset, then open the existing add screen.

The wait uses the hub that is already listening. It does not open a socket.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..b_logicx.detect import DETECT_WAIT_S, configured_bus_keys
from ..const import *
from .common import _flow_lang, _placeholders

_LOGGER = logging.getLogger(__name__)


class DetectSteps:
    """Options steps for Detect an address.

    Mixed into BLogicxOptionsFlow. RLM, SoftM, and cover then reuse their
    add screens, with the address filled in.
    """

    def _running_hub(self) -> Any:
        """The hub for this entry, or None when the integration is not running."""
        return self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)

    def _on_off_word(self, turned_on: bool) -> str:
        if _flow_lang(self.hass) == "nl":
            return "aan" if turned_on else "uit"
        return "on" if turned_on else "off"

    async def async_step_detect_address(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Tell the user to be ready. The button starts the wait."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._running_hub() is None:
                errors["base"] = "detect_not_running"
            else:
                self._detect_task = None
                self._detected = None
                return await self.async_step_detect_wait()
        return self.async_show_form(
            step_id="detect_address",
            data_schema=vol.Schema({}),
            errors=errors or None,
            description_placeholders=_placeholders(),
        )

    async def async_step_detect_wait(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Spinner until the first unknown Set or Reset, or until the wait ends."""
        task: asyncio.Task | None = getattr(self, "_detect_task", None)
        if task is None:
            self._detect_task = self.hass.async_create_task(self._async_detect_wait())
            task = self._detect_task
        if not task.done():
            return self.async_show_progress(
                step_id="detect_wait",
                progress_action="detect_wait",
                description_placeholders=_placeholders(),
                progress_task=task,
            )
        self._detect_task = None
        if task.cancelled():
            return self.async_show_progress_done(next_step_id="detect_timeout")
        try:
            found = task.result()
        except Exception:
            _LOGGER.exception("Detect wait failed")
            found = None
        if not found:
            return self.async_show_progress_done(next_step_id="detect_timeout")
        self._detected = found
        return self.async_show_progress_done(next_step_id="detect_kind")

    async def _async_detect_wait(self) -> tuple[int, int, bool] | None:
        """Block until one matching frame, or DETECT_WAIT_S. None on timeout."""
        hub = self._running_hub()
        if hub is None:
            return None
        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        future = hub.begin_detect(configured_bus_keys(addresses))
        try:
            await asyncio.wait({future}, timeout=DETECT_WAIT_S)
        finally:
            hub.end_detect(future)
        if future.cancelled() or not future.done():
            return None
        return future.result()

    async def async_step_detect_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Nothing new arrived. Another try shows the ready reminder again."""
        if user_input is not None:
            return await self.async_step_detect_address()
        return self.async_show_form(
            step_id="detect_timeout",
            data_schema=vol.Schema({}),
            description_placeholders=_placeholders(),
        )

    async def async_step_detect_kind(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask RLM, SoftM, or cover, then open that add screen filled in."""
        found = getattr(self, "_detected", None)
        if not found:
            return await self.async_step_detect_address()
        group, address, turned_on = found
        if user_input is not None:
            kind = user_input.get("address_type", ADDRESS_TYPE_RLM)
            if kind == ADDRESS_TYPE_SHUTTER:
                # Close stays for the user. Only the up relay was seen.
                self._edit_defaults = {
                    "open_group": group,
                    "open_address": address,
                }
                return await self.async_step_add_shutter_detect()
            self._edit_defaults = {"group": group, "address": address}
            if kind == ADDRESS_TYPE_SOFTM:
                return await self.async_step_add_softm()
            return await self.async_step_add_rlm()
        return self.async_show_form(
            step_id="detect_kind",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address_type", default=ADDRESS_TYPE_RLM
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                ADDRESS_TYPE_RLM,
                                ADDRESS_TYPE_SOFTM,
                                ADDRESS_TYPE_SHUTTER,
                            ],
                            translation_key="address_type",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(
                group=group,
                address=address,
                state=self._on_off_word(turned_on),
            ),
        )
