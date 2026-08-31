"""B-Logicx hub that manages the connection to one BL-NWM gateway.
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
    VALUE_MAX_AGE_S,
    LdmReading,
    MeasureBusState,
    TsmReading,
    heat_requested_from_system,
)

_LOGGER = logging.getLogger(__name__)

# Status wait: long enough for a slow bus device, short enough not to stall setup.
# Matches the ~2s gaps seen when replies were lost due to framing desync; with a
# single shared receiver those gaps should no longer mean a permanent miss.
_STATUS_TIMEOUT = 2.5
# Brief settle after each Status exchange before the next address is queried.
_STATUS_GAP = 0.05
_MEASURE_TIMEOUT = 2.5


class BLogicxHub:
    """Manages a single connection + distributes events to listeners."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self._conn: BLXConnection | None = None
        self._listener_task: asyncio.Task | None = None
        # Keyed by (group, address) for early filtering of irrelevant datagrams
        self._listeners: dict[tuple[int, int], list[Callable[[BLXEvent], None]]] = {}
        # Serialise Status queries: one Status at a time, wait for Set/Reset
        # before sending the next. Parallel Status storms lose replies.
        self._status_lock = asyncio.Lock()
        self._pending_status: dict[tuple[int, int], asyncio.Future] = {}
        # Serialise multi-frame TX (e.g. RTC Program sequences)
        self._tx_lock = asyncio.Lock()
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
        # Last TSM identity for heat-requested association
        self._last_tsm_identity: tuple[int, int] | None = None

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

                # Resolve any in-flight Status wait for this address
                if event.command in ("Set", "Reset") and key in self._pending_status:
                    fut = self._pending_status[key]
                    if not fut.done():
                        fut.set_result(event.command == "Set")

                self._handle_measure_event(event, now)

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

    def _handle_measure_event(self, event: BLXEvent, now: float) -> None:
        cmd = event.command
        g, a = event.group, event.address

        if cmd == "Value":
            # Dual sticky: group 11 → TSM temp; else → LDM light payload
            self._measure.note_value(g, a, now)
            return

        if cmd == "Settings":
            self._measure.note_settings(g, a, now)
            return

        if cmd == "Data":
            # TSM Data 0.26 is a fixed handshake marker — ignore for temperature
            return

        if cmd == "System":
            heat = heat_requested_from_system(g, a)
            if heat is not None:
                tkey = self._last_tsm_identity
                if tkey is not None and tkey in self._tsm_keys:
                    full = self._measure.try_tsm_reading(
                        tkey[0], tkey[1], now, heat=heat
                    )
                    if full is not None:
                        self._dispatch_tsm(tkey, full)
                    else:
                        self._dispatch_tsm(
                            tkey,
                            self._measure.heat_only_reading(tkey[0], tkey[1], heat),
                        )
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
                self._last_tsm_identity = key
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

    def _dispatch_ldm(self, key: tuple[int, int], reading: LdmReading) -> None:
        fut = self._pending_ldm.get(key)
        if fut is not None and not fut.done():
            fut.set_result(reading)
        for cb in list(self._ldm_callbacks.get(key, [])):
            try:
                cb(reading)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("LDM callback error")

    def _dispatch_tsm(self, key: tuple[int, int], reading: TsmReading) -> None:
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
        """Send a command on the bus."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        await self._conn.send(command, group, address)

    async def async_send_sequence(
        self,
        frames: list[tuple[str, int, int]],
        *,
        inter_frame_delay: float = 0.01,
    ) -> None:
        """Send multiple datagrams under the TX lock (e.g. RTC Program write)."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        async with self._tx_lock:
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
            busy = bool(self._pending_status) or self._status_lock.locked()
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

        Status queries are serialised with a lock so only one is in flight
        at a time. Returns True if the device reported Set (on), False for
        Reset (off), or None on timeout / cancel.

        Even after a timeout, a late Set/Reset will still update the entity
        via its normal listener — only the Future wait is abandoned.
        """
        async with self._status_lock:
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
                # Small gap so the next Status is not back-to-back on a busy bus
                try:
                    await asyncio.sleep(_STATUS_GAP)
                except asyncio.CancelledError:
                    pass

    async def async_request_ldm(
        self, group: int, address: int, *, timeout: float = _MEASURE_TIMEOUT
    ) -> LdmReading | None:
        """Request LDM reading: Data 0.2 then Select g.a; wait for Value+System."""
        key = (group, address)
        async with self._tx_lock:
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

    async def async_request_tsm(
        self, group: int, address: int, *, timeout: float = _MEASURE_TIMEOUT
    ) -> TsmReading | None:
        """Request TSM burst via Status g.a; wait for decoded reading."""
        key = (group, address)
        async with self._tx_lock:
            if self._conn is None:
                raise RuntimeError("Not connected")
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            old = self._pending_tsm.get(key)
            if old is not None and not old.done():
                old.cancel()
            self._pending_tsm[key] = fut
            try:
                _LOGGER.debug("TSM request → Status %s.%s", group, address)
                await self._conn.send("Status", group, address)
                reading: TsmReading = await asyncio.wait_for(fut, timeout=timeout)
                return reading
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "No TSM reply for %s.%s within %.1fs", group, address, timeout
                )
                return None
            except asyncio.CancelledError:
                return None
            finally:
                if self._pending_tsm.get(key) is fut:
                    self._pending_tsm.pop(key, None)
