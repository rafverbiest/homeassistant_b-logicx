"""Detect one unknown Set or Reset, then open the existing add screen.

The wait uses the hub that is already listening. It does not open a socket.
A cover then listens again: up is the Set from the first press, down is the
Set from the second. Reset is the other relay and is not stored as either.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from ..b_logicx.detect import (
    DETECT_SETTLE_S,
    DETECT_WAIT_S,
    configured_bus_keys,
    shown_detect_frame,
)
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

    def _detect_known(self) -> set[tuple[int, int]]:
        """Saved pairs, plus the up relay once a cover listen is looking for down."""
        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        known = configured_bus_keys(addresses)
        exclude = getattr(self, "_detect_exclude", None)
        if exclude is not None and getattr(self, "_detect_phase", "first") != "first":
            known.add(tuple(exclude))
        return known

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
                self._detect_set = None
                self._detect_exclude = None
                self._detect_phase = "first"
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
        """Spinner until the listen finishes, or until the wait ends."""
        task: asyncio.Task | None = getattr(self, "_detect_task", None)
        if task is None:
            self._detect_task = self.hass.async_create_task(self._async_detect_wait())
            task = self._detect_task
        phase = getattr(self, "_detect_phase", "first")
        if phase == "close":
            progress_action = "detect_close_wait"
        elif phase == "up":
            progress_action = "detect_up_wait"
        else:
            progress_action = "detect_wait"
        if not task.done():
            return self.async_show_progress(
                step_id="detect_wait",
                progress_action=progress_action,
                description_placeholders=_placeholders(),
                progress_task=task,
            )
        self._detect_task = None
        if task.cancelled():
            return self.async_show_progress_done(next_step_id=self._detect_miss_step())
        try:
            found = task.result()
        except Exception:
            _LOGGER.exception("Detect wait failed")
            found = None
        if not found:
            return self.async_show_progress_done(next_step_id=self._detect_miss_step())
        if phase == "close":
            up = getattr(self, "_detect_exclude", None)
            if not up:
                return self.async_show_progress_done(next_step_id="detect_address")
            group, address, _turned_on = found
            self._edit_defaults = {
                "open_group": up[0],
                "open_address": up[1],
                "close_group": group,
                "close_address": address,
            }
            return self.async_show_progress_done(next_step_id="add_shutter")
        if phase == "up":
            group, address, _turned_on = found
            self._detect_set = found
            self._detect_exclude = (group, address)
            self._edit_defaults = {"open_group": group, "open_address": address}
            return self.async_show_progress_done(next_step_id="detect_close")
        self._detected = found
        return self.async_show_progress_done(next_step_id="detect_kind")

    def _detect_miss_step(self) -> str:
        """Where a listen that heard nothing useful goes back to."""
        phase = getattr(self, "_detect_phase", "first")
        if phase == "close":
            return "detect_close_timeout"
        if phase == "up":
            return "detect_up_again"
        return "detect_timeout"

    async def _async_detect_wait(self) -> tuple[int, int, bool] | None:
        """Block until the frame this phase wants, or DETECT_WAIT_S. None on timeout."""
        hub = self._running_hub()
        if hub is None:
            return None
        try:
            phase = getattr(self, "_detect_phase", "first")
            if phase == "first":
                return await self._async_detect_first(hub)
            return await self._async_listen_one(
                hub,
                self._detect_known(),
                set_only=True,
                hold_stash=False,
                timeout=DETECT_WAIT_S,
            )
        finally:
            hub.end_detect()

    async def _async_detect_first(self, hub: Any) -> tuple[int, int, bool] | None:
        """First Set or Reset, then a brief extra listen so a following Set is kept."""
        known = self._detect_known()
        first = await self._async_listen_one(
            hub,
            known,
            set_only=False,
            hold_stash=True,
            timeout=DETECT_WAIT_S,
        )
        if first is None:
            return None
        frames = [first]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + DETECT_SETTLE_S
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            nxt = await self._async_listen_one(
                hub,
                known,
                set_only=False,
                hold_stash=True,
                timeout=remaining,
            )
            if nxt is None:
                break
            frames.append(nxt)
        shown = shown_detect_frame(frames)
        self._detect_set = next((frame for frame in frames if frame[2]), None)
        return shown

    async def _async_listen_one(
        self,
        hub: Any,
        known: set[tuple[int, int]],
        *,
        set_only: bool,
        hold_stash: bool,
        timeout: float,
    ) -> tuple[int, int, bool] | None:
        """One matching frame, or None when the timeout expires first."""
        future = hub.begin_detect(known, set_only=set_only, hold_stash=hold_stash)
        await asyncio.wait({future}, timeout=timeout)
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
        """Ask RLM, SoftM, or cover. Cover keeps only a Set as the up relay."""
        found = getattr(self, "_detected", None)
        if not found:
            return await self.async_step_detect_address()
        group, address, turned_on = found
        if user_input is not None:
            kind = user_input.get("address_type", ADDRESS_TYPE_RLM)
            if kind == ADDRESS_TYPE_SHUTTER:
                found_set = getattr(self, "_detect_set", None)
                if not found_set:
                    return await self.async_step_detect_up_again()
                up_group, up_address, _turned_on = found_set
                self._detect_exclude = (up_group, up_address)
                self._edit_defaults = {
                    "open_group": up_group,
                    "open_address": up_address,
                }
                return await self.async_step_detect_close()
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

    async def async_step_detect_up_again(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Cover was chosen and the first press was only a Reset. Ask for up again."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._running_hub() is None:
                errors["base"] = "detect_not_running"
            else:
                self._detect_task = None
                self._detect_phase = "up"
                return await self.async_step_detect_wait()
        return self.async_show_form(
            step_id="detect_up_again",
            data_schema=vol.Schema({}),
            errors=errors or None,
            description_placeholders=_placeholders(),
        )

    async def async_step_detect_close(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Up is known. The button starts the listen for the down Set."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._running_hub() is None:
                errors["base"] = "detect_not_running"
            else:
                self._detect_task = None
                self._detect_phase = "close"
                return await self.async_step_detect_wait()
        return self.async_show_form(
            step_id="detect_close",
            data_schema=vol.Schema({}),
            errors=errors or None,
            description_placeholders=_placeholders(),
        )

    async def async_step_detect_close_timeout(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Down Set did not arrive. Listen again, or type the down relay."""
        return self.async_show_menu(
            step_id="detect_close_timeout",
            menu_options=["detect_close", "detect_close_manual"],
            description_placeholders=_placeholders(),
        )

    async def async_step_detect_close_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Open the cover form with the up relay filled in and down left to type."""
        exclude = getattr(self, "_detect_exclude", None)
        if not exclude:
            return await self.async_step_detect_address()
        group, address = exclude
        self._edit_defaults = {"open_group": group, "open_address": address}
        return await self.async_step_add_shutter_detect()
