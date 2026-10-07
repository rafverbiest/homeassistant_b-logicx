"""Home Assistant's one voice on a single BL-NWM gateway.

This is the "Pièce de résistance" of this implentation :)

Each datagram is handled in this order:

1. A Status query that is waiting for Set or Reset on this address.
2. The SoftM virtual status module, which may answer on the bus.
3. The LDM / TSM decoder.
4. The BL-AUD decoder.
5. Entity callbacks registered for this group.address.

Status, an LDM request, a TSM request, a BL-AUD command, an RTC write, and a
frame the repeater forwards all share one lock, so they cannot cut into each
other. A SoftM reply does not take that lock: it is sent from the listener,
and the listener is what a Status wait is blocked on.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from homeassistant.core import HomeAssistant

from .b_logicx import BLXConnection, BLXEvent
from .b_logicx.measure import (
    LDM_REQUEST_DATA_ADDRESS,
    LDM_REQUEST_DATA_GROUP,
    LdmReading,
    MeasureBusState,
    TsmReading,
)
from .b_logicx.audio import AUD_MISC_GROUP, AudBusState, AudCommand
from .b_logicx.softm_tracker import SoftMConfig, SoftMTracker
from .bus_repeater import BusRepeater
from .const import DEFAULT_BUS_REPEATER_PORT

_LOGGER = logging.getLogger(__name__)

# Status wait: long enough for a slow bus device, short enough not to stall setup.
_STATUS_TIMEOUT = 2.5
# On integration statup, we query each address that has the option 'Check status'
# set to On. This causes some traffic on the bus when many addresses need to be queried.
# B-Logicx datagrams unfortunately tend to collide when the bus is busy.
# One would think we live in a time where CSMA is commonplace, old-school technology,
# but in certain areas of Belgium people like to reinvent the wheel, poorly.
#
# I absolutely loathe having to do this (the real fix needs to happen in the hardware)
# but we do not control that. So, to get around this, we need to slow down.
#
# After each request/response (Status, LDM, TSM), pause before the next transaction.
# 50 ms seems to be enough for most hardware but Sfeers intermittently
# missed Set/Resets; 100 ms seems to be more reliable on a busy startup queue.
_STATUS_GAP = 0.10  # 100 ms
_MEASURE_TIMEOUT = 2.5


class BLogicxHub:
    """The listener, the request lock, and the registries for one gateway."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self._conn: BLXConnection | None = None
        self._listener_task: asyncio.Task | None = None
        # Keyed by (group, address) for early filtering of irrelevant datagrams
        self._listeners: dict[tuple[int, int], list[Callable[[BLXEvent], None]]] = {}
        # ONE lock for all bus request/response pairs (Status, LDM, TSM, RTC sequence).
        # Prevents LDM Data/Select from interleaving mid Status-wait (missed Set/Reset).
        self._request_lock = asyncio.Lock()
        self._pending_status: dict[tuple[int, int], asyncio.Future] = {}
        # Last successful RTC sync per (group, address) → datetime (UTC-aware optional)
        self.rtc_last_sync: dict[tuple[int, int], object] = {}
        self._rtc_sync_callbacks: list = []
        # LDM / TSM multi-frame decode
        self._measure = MeasureBusState()
        self._ldm_keys: set[tuple[int, int]] = set()
        self._tsm_keys: set[tuple[int, int]] = set()
        self._ldm_callbacks: dict[
            tuple[int, int], list[Callable[[LdmReading], None]]
        ] = {}
        self._tsm_callbacks: dict[
            tuple[int, int], list[Callable[[TsmReading], None]]
        ] = {}
        self._pending_ldm: dict[tuple[int, int], asyncio.Future] = {}
        self._pending_tsm: dict[tuple[int, int], asyncio.Future] = {}
        self._aud = AudBusState()
        self._aud_keys: set[tuple[int, int]] = set()
        self._aud_callbacks: dict[
            tuple[int, int], list[Callable[[AudCommand], None]]
        ] = {}
        # SoftM virtual status tracking
        self._softm = SoftMTracker()
        self._softm_enabled = False
        self._softm_timer_tasks: dict[tuple[int, int], asyncio.Task] = {}
        # Keys whose next Set/Reset is our SoftM reply echo (do not cancel timer)
        self._softm_own_emit: set[tuple[int, int]] = set()
        self._repeater: BusRepeater | None = None

    def configure_softm_tracking(
        self, enabled: bool, configs: list[SoftMConfig]
    ) -> None:
        """Turn virtual status tracking on, or clear it when the master switch is off."""
        self._softm_enabled = enabled
        if enabled:
            self._softm.configure(configs)
        else:
            self._softm.configure([])

    def softm_seed(self, group: int, address: int, is_on: bool) -> None:
        """Overwrite SoftM memory, for example from a restored on/off."""
        self._softm.seed(group, address, is_on)

    def softm_get_state(self, group: int, address: int) -> bool | None:
        """Remembered on/off for a tracked SoftM, or None."""
        return self._softm.get_state(group, address)

    def register_listener(
        self, callback: Callable[[BLXEvent], None], group: int, address: int
    ) -> Callable[[], None]:
        """Register a callback for events on a specific address.

        Events for other addresses are discarded early in the hub for efficiency.
        Returns an unregister function.
        """
        key = (group, address)
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(callback)

        def unregister() -> None:
            if key in self._listeners and callback in self._listeners[key]:
                self._listeners[key].remove(callback)
                if not self._listeners[key]:
                    del self._listeners[key]

        return unregister

    def register_ldm(
        self, group: int, address: int, callback: Callable[[LdmReading], None]
    ) -> Callable[[], None]:
        """An LDM. System on this group.address commits a light reading."""
        key = (group, address)
        self._ldm_keys.add(key)
        self._ldm_callbacks.setdefault(key, []).append(callback)

        def _unreg() -> None:
            cbs = self._ldm_callbacks.get(key)
            if cbs and callback in cbs:
                cbs.remove(callback)
            if not cbs:
                self._ldm_callbacks.pop(key, None)
                self._ldm_keys.discard(key)

        return _unreg

    def register_tsm(
        self, group: int, address: int, callback: Callable[[TsmReading], None]
    ) -> Callable[[], None]:
        """A TSM. System on this group.address commits the temperature."""
        key = (group, address)
        self._tsm_keys.add(key)
        self._tsm_callbacks.setdefault(key, []).append(callback)

        def _unreg() -> None:
            cbs = self._tsm_callbacks.get(key)
            if cbs and callback in cbs:
                cbs.remove(callback)
            if not cbs:
                self._tsm_callbacks.pop(key, None)
                self._tsm_keys.discard(key)

        return _unreg

    async def async_start(self) -> None:
        """Start listening to the bus.

        Uses the BLXConnection singleton so it is technically impossible to
        open more than one TCP connection to the same gateway (host:port).
        The connection runs a **single** background reader; this hub only
        subscribes to its event stream (safe if start is called more than once).
        """
        if self._conn is not None:
            if getattr(self._conn, "_writer", None) is not None and not getattr(
                self._conn, "_closed", False
            ):
                pass
            else:
                self._conn = None

        self._conn = BLXConnection(self.host, self.port)
        await self._conn.connect()

        # Idempotent: never run two hub listener tasks on the same hub
        if self._listener_task is not None and not self._listener_task.done():
            _LOGGER.debug("B-Logicx hub listener already running for %s", self.host)
            return

        self._listener_task = self.hass.async_create_background_task(
            self._listen_forever(), name="b_logicx_listener"
        )
        _LOGGER.info("Started B-Logicx listener for %s", self.host)

    async def _listen_forever(self) -> None:
        assert self._conn is not None
        try:
            async for event in self._conn.events():
                key = (event.group, event.address)
                now = time.monotonic()

                # Finish a waiting Status before SoftM looks at the same frame.
                if event.command in ("Set", "Reset") and key in self._pending_status:
                    fut = self._pending_status[key]
                    if not fut.done():
                        fut.set_result(event.command == "Set")
                        _LOGGER.debug(
                            "Status matched ← %s %s.%s",
                            event.command,
                            event.group,
                            event.address,
                        )

                # SoftM VSM before measure (may emit Set/Reset)
                if self._softm_enabled:
                    await self._handle_softm_event(event)

                self._handle_measure_event(event, now)
                self._handle_aud_event(event, now)

                if key in self._listeners:
                    for callback in list(self._listeners[key]):
                        try:
                            callback(event)
                        except Exception:  # noqa: BLE001
                            _LOGGER.exception("Error in B-Logicx event listener")
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("B-Logicx listener error: %s", err)

    async def _softm_send(self, command: str, group: int, address: int) -> None:
        """Send a SoftM reply; mark so the RX echo does not cancel SoftM timers."""
        key = (group, address)
        self._softm_own_emit.add(key)
        try:
            await self.async_send(command, group, address)
        except Exception:
            self._softm_own_emit.discard(key)
            raise
        # If the gateway never echoes TX, clear the mark so a later external
        # Set/Reset still cancels SoftM timers.
        asyncio.create_task(
            self._softm_own_emit_expire(key),
            name=f"softm_own_emit_{group}_{address}",
        )

    async def _softm_own_emit_expire(self, key: tuple[int, int]) -> None:
        """Forget our own echo mark after 150 ms if the gateway never sent it back."""
        try:
            await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            return
        self._softm_own_emit.discard(key)

    def _softm_cancel_timer_task(self, group: int, address: int) -> None:
        """Stop the waiting task so expiry will not send Reset."""
        key = (group, address)
        task = self._softm_timer_tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
        self._softm.cancel_timer(group, address)

    async def _handle_softm_event(self, event: BLXEvent) -> None:
        """Virtual SoftM status tracking (Toggle/Status/Timer/Set/Reset)."""
        g, a = event.group, event.address
        if not self._softm.is_tracked(g, a):
            return
        cmd = event.command
        key = (g, a)

        if cmd in ("Set", "Reset"):
            # This is where a timer obeys Reset. An outside Set or Reset cancels
            # it. The Set/Reset we just sent ourselves (timer start, Status
            # reply, Toggle reply, expiry) is marked for 150 ms and does not.
            own_echo = key in self._softm_own_emit
            if own_echo:
                self._softm_own_emit.discard(key)
            else:
                self._softm_cancel_timer_task(g, a)
            self._softm.on_set_reset(g, a, cmd == "Set")
            return

        if cmd == "Toggle":
            self._softm_cancel_timer_task(g, a)
            action = self._softm.on_toggle(g, a)
            if action is not None:
                await self._softm_send(action.command, action.group, action.address)
            return

        if cmd == "Status":
            # Query only — do not cancel SoftM timer; reply from memory.
            action = self._softm.on_status(g, a)
            if action is not None:
                await self._softm_send(action.command, action.group, action.address)
            return

        if cmd == "Timer":
            result = self._softm.on_timer(g, a)
            if result is None:
                return
            action, secs = result
            old = self._softm_timer_tasks.pop(key, None)
            if old is not None and not old.done():
                old.cancel()
            await self._softm_send(action.command, action.group, action.address)
            self._softm_timer_tasks[key] = asyncio.create_task(
                self._softm_timer_fire(g, a, secs),
                name=f"softm_timer_{g}_{a}",
            )

    async def _softm_timer_fire(self, group: int, address: int, secs: float) -> None:
        """When the delay ends, send Reset unless the timer was cancelled."""
        try:
            await asyncio.sleep(secs)
        except asyncio.CancelledError:
            return
        action = self._softm.timer_expired(group, address)
        self._softm_timer_tasks.pop((group, address), None)
        if action is not None:
            try:
                await self._softm_send(action.command, action.group, action.address)
            except Exception:
                _LOGGER.exception("SoftM timer Reset failed for %s.%s", group, address)

    def _handle_measure_event(self, event: BLXEvent, now: float) -> None:
        """LDM: Value(≠11)+System. TSM: Value 11 + Settings + System only."""
        cmd = event.command
        g, a = event.group, event.address

        if cmd == "Value":
            self._measure.note_value(g, a, now)
            return

        if cmd == "Settings":
            self._measure.note_settings(g, a, now)
            return

        # Value and Settings were stored above. Only System can commit them,
        # and only when this group.address is a registered LDM or TSM.
        if cmd != "System":
            return

        key = (g, a)
        if key in self._ldm_keys:
            ldm = self._measure.try_ldm_reading(g, a, now)
            if ldm is not None:
                _LOGGER.debug(
                    "LDM %s.%s raw=%s percent=%.2f (from Value %s.%s)",
                    g,
                    a,
                    ldm.raw,
                    ldm.percent,
                    ldm.value_group,
                    ldm.value_address,
                )
                self._dispatch_ldm(key, ldm)
            return

        if key in self._tsm_keys:
            reading = self._measure.try_tsm_reading(g, a, now)
            if reading is not None:
                _LOGGER.debug(
                    "TSM %s.%s temperature=%.1f°C (from Value 11.%s)",
                    g,
                    a,
                    reading.temperature_c,
                    reading.value_address,
                )
                self._dispatch_tsm(key, reading)
            return

    def register_aud(
        self,
        group: int,
        address: int,
        callback: Callable[[AudCommand], None],
    ) -> Callable[[], None]:
        """A BL-AUD. Select on this group.address commits the pending Misc."""
        key = (group, address)
        self._aud_keys.add(key)
        self._aud_callbacks.setdefault(key, []).append(callback)

        def _unreg() -> None:
            cbs = self._aud_callbacks.get(key, [])
            if callback in cbs:
                cbs.remove(callback)
            if not cbs:
                self._aud_keys.discard(key)
                self._aud_callbacks.pop(key, None)

        return _unreg

    def _handle_aud_event(self, event: BLXEvent, now: float) -> None:
        """Hand the frame to the one Misc slot. A committed command updates the player."""
        cmd = self._aud.note(
            event.command,
            event.group,
            event.address,
            now,
            aud_keys=self._aud_keys,
        )
        if cmd is None:
            return
        key = (cmd.group, cmd.address)
        _LOGGER.debug("AUD %s.%s code=%s", cmd.group, cmd.address, cmd.code)
        for cb in list(self._aud_callbacks.get(key, [])):
            try:
                cb(cmd)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("AUD callback error")

    async def async_send_aud(self, group: int, address: int, code: int) -> None:
        """Send Misc 0.code, wait 10 ms, then Select the player, under the request lock.

        The gap gives the module a moment to see the Misc before Select.
        """
        if self._conn is None:
            raise RuntimeError("Not connected")
        async with self._request_lock:
            await self._conn.send("Misc", AUD_MISC_GROUP, int(code) & 0xFF)
            await asyncio.sleep(0.01)
            await self._conn.send("Select", group, address)

    def _dispatch_ldm(self, key: tuple[int, int], reading: LdmReading) -> None:
        """Wake a waiting LDM request and tell every callback for this sensor."""
        fut = self._pending_ldm.get(key)
        if fut is not None and not fut.done():
            fut.set_result(reading)
        for cb in list(self._ldm_callbacks.get(key, [])):
            try:
                cb(reading)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("LDM callback error")

    def _dispatch_tsm(self, key: tuple[int, int], reading: TsmReading) -> None:
        """Wake a waiting TSM request and tell every callback for this thermostat."""
        fut = self._pending_tsm.get(key)
        if fut is not None and not fut.done():
            fut.set_result(reading)
        for cb in list(self._tsm_callbacks.get(key, [])):
            try:
                cb(reading)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("TSM callback error")

    async def async_stop(self) -> None:
        """Stop listening.

        IMPORTANT: we intentionally do NOT close the underlying connection.
        The BLXConnection singleton keeps the TCP socket alive. On the next
        setup the new hub will obtain the *same* open connection via the
        singleton and only (re)subscribe its listener.
        """
        if self._listener_task:
            if not self._listener_task.done():
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass
            self._listener_task = None

        for fut in list(self._pending_status.values()):
            if not fut.done():
                fut.cancel()
        self._pending_status.clear()
        for fut in list(self._pending_ldm.values()):
            if not fut.done():
                fut.cancel()
        self._pending_ldm.clear()
        for fut in list(self._pending_tsm.values()):
            if not fut.done():
                fut.cancel()
        self._pending_tsm.clear()
        self._listeners.clear()
        self._ldm_callbacks.clear()
        self._tsm_callbacks.clear()
        self._ldm_keys.clear()
        self._tsm_keys.clear()
        self._aud_callbacks.clear()
        self._aud_keys.clear()
        self._aud = AudBusState()
        for task in list(self._softm_timer_tasks.values()):
            if not task.done():
                task.cancel()
        self._softm_timer_tasks.clear()
        self._softm_own_emit.clear()
        await self.async_stop_repeater()

    async def async_start_repeater(
        self, *, port: int = DEFAULT_BUS_REPEATER_PORT, allow_cidr: str | None = None
    ) -> None:
        """Let BLConfig or blxmonitor share this gateway connection.

        Frames they send take the same request lock as Status and the sensors.
        """
        if self._conn is None:
            raise RuntimeError("Not connected")
        await self.async_stop_repeater()
        self._repeater = BusRepeater(
            self._conn,
            self.host,
            port=port,
            allow_cidr=allow_cidr,
            request_lock=self._request_lock,
        )
        await self._repeater.start()

    async def async_stop_repeater(self) -> None:
        """Close the repeater listener. The gateway connection stays open."""
        if self._repeater is not None:
            await self._repeater.stop()
            self._repeater = None

    async def async_close(self) -> None:
        """Fully tear down the connection. Use only on integration removal or shutdown."""
        await self.async_stop()
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def async_send(self, command: str, group: int, address: int) -> None:
        """Write one datagram without the request lock.

        SoftM answers from the listener. Taking the lock here could deadlock
        a Status wait that holds the lock until this listener runs.
        """
        if self._conn is None:
            raise RuntimeError("Not connected")
        await self._conn.send(command, group, address)

    async def async_send_sequence(
        self,
        frames: list[tuple[str, int, int]],
        *,
        inter_frame_delay: float = 0.01,
    ) -> None:
        """Send multiple datagrams under the request lock (e.g. RTC Program write)."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        async with self._request_lock:
            for i, (command, group, address) in enumerate(frames):
                if inter_frame_delay and i:
                    await asyncio.sleep(inter_frame_delay)
                await self._conn.send(command, group, address)

    def register_rtc_sync_callback(self, callback) -> Callable[[], None]:
        """Notify HA entities when an RTC last_sync timestamp updates."""
        self._rtc_sync_callbacks.append(callback)

        def _unreg() -> None:
            if callback in self._rtc_sync_callbacks:
                self._rtc_sync_callbacks.remove(callback)

        return _unreg

    def notify_rtc_synced(self, group: int, address: int, when) -> None:
        """Remember when this clock was written and tell the RTC entity."""
        self.rtc_last_sync[(group, address)] = when
        for cb in list(self._rtc_sync_callbacks):
            try:
                cb(group, address, when)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("RTC sync callback error")

    async def async_wait_until_status_idle(
        self, *, quiet_for: float = 0.5, timeout: float = 60.0
    ) -> None:
        """Wait until no Status queries are in flight for *quiet_for* seconds.

        Used so RTC startup sync runs after initial entity Status probes.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        quiet_since: float | None = None
        while loop.time() < deadline:
            busy = (
                bool(self._pending_status)
                or bool(self._pending_ldm)
                or bool(self._pending_tsm)
                or self._request_lock.locked()
            )
            if not busy:
                if quiet_since is None:
                    quiet_since = loop.time()
                elif loop.time() - quiet_since >= quiet_for:
                    return
            else:
                quiet_since = None
            await asyncio.sleep(0.05)
        _LOGGER.debug(
            "Status idle wait timed out after %.1fs; proceeding anyway", timeout
        )

    async def async_request_status(
        self, group: int, address: int, *, timeout: float = _STATUS_TIMEOUT
    ) -> bool | None:
        """Send Status and wait for the matching Set/Reset reply.

        Serialised with LDM/TSM/RTC on ``_request_lock`` so no other TX can
        interleave while waiting for Set/Reset.

        Returns True if Set (on), False if Reset (off), None on timeout/cancel.
        """
        async with self._request_lock:
            if self._conn is None:
                raise RuntimeError("Not connected")

            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            key = (group, address)

            old = self._pending_status.get(key)
            if old is not None and not old.done():
                old.cancel()
            self._pending_status[key] = fut

            try:
                _LOGGER.debug("Status query → %s.%s", group, address)
                await self.async_send("Status", group, address)
                is_on: bool = await asyncio.wait_for(fut, timeout=timeout)
                _LOGGER.debug(
                    "Status reply ← %s.%s is_on=%s", group, address, is_on
                )
                return is_on
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No Set/Reset response to Status for %s.%s within %.1fs "
                    "(entity may still update if a late reply arrives)",
                    group,
                    address,
                    timeout,
                )
                return None
            except asyncio.CancelledError:
                return None
            finally:
                if self._pending_status.get(key) is fut:
                    self._pending_status.pop(key, None)
                try:
                    await asyncio.sleep(_STATUS_GAP)
                except asyncio.CancelledError:
                    pass

    async def async_request_ldm(
        self, group: int, address: int, *, timeout: float = _MEASURE_TIMEOUT
    ) -> LdmReading | None:
        """Ask an LDM for a reading: Data 0.2, 10 ms, then Select, and wait.

        The module answers with Value and then System. System commits the reading.
        """
        key = (group, address)
        async with self._request_lock:
            if self._conn is None:
                raise RuntimeError("Not connected")
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            old = self._pending_ldm.get(key)
            if old is not None and not old.done():
                old.cancel()
            self._pending_ldm[key] = fut
            try:
                _LOGGER.debug("LDM request → Data 0.2 + Select %s.%s", group, address)
                await self._conn.send(
                    "Data", LDM_REQUEST_DATA_GROUP, LDM_REQUEST_DATA_ADDRESS
                )
                await asyncio.sleep(0.01)
                await self._conn.send("Select", group, address)
                reading: LdmReading = await asyncio.wait_for(fut, timeout=timeout)
                return reading
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No LDM reply for %s.%s within %.1fs", group, address, timeout
                )
                return None
            except asyncio.CancelledError:
                return None
            finally:
                if self._pending_ldm.get(key) is fut:
                    self._pending_ldm.pop(key, None)
                try:
                    await asyncio.sleep(_STATUS_GAP)
                except asyncio.CancelledError:
                    pass

    async def async_request_tsm(
        self, group: int, address: int, *, timeout: float = _MEASURE_TIMEOUT
    ) -> TsmReading | None:
        """Ask a TSM for a reading by sending Status, then wait for the triple.

        The module answers Value 11, Settings, and System. System commits it.
        """
        key = (group, address)
        async with self._request_lock:
            if self._conn is None:
                raise RuntimeError("Not connected")
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            old = self._pending_tsm.get(key)
            if old is not None and not old.done():
                old.cancel()
            self._pending_tsm[key] = fut
            try:
                _LOGGER.debug(
                    "TSM request → Status %s.%s (expect Value 11 + Settings + System)",
                    group,
                    address,
                )
                await self._conn.send("Status", group, address)
                reading: TsmReading = await asyncio.wait_for(fut, timeout=timeout)
                return reading
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No TSM triple for %s.%s within %.1fs", group, address, timeout
                )
                return None
            except asyncio.CancelledError:
                return None
            finally:
                if self._pending_tsm.get(key) is fut:
                    self._pending_tsm.pop(key, None)
                try:
                    await asyncio.sleep(_STATUS_GAP)
                except asyncio.CancelledError:
                    pass
