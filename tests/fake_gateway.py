"""Adversarial fake BL-NWM TCP gateway for offline tests.

Speaks the same 2-byte datagram protocol. Can answer Status from a state map,
simulate Sfeer exclusivity, delay replies, drop Status, and inject scripted
traffic to try to confuse the client.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from b_logicx.bus_format import format_recv, format_sent
from b_logicx.models import BLXEvent
from b_logicx.protocol import decode_datagram, encode_datagram

_LOGGER = logging.getLogger(__name__)
_BUS_LOGGER = logging.getLogger("b_logicx.tests.bus")

OnCommand = Callable[["FakeGateway", BLXEvent], Awaitable[None] | None]
BusLogCallback = Callable[[str], None]


@dataclass
class FakeGateway:
    """TCP server pretending to be a BL-NWM."""

    host: str = "127.0.0.1"
    port: int = 0  # 0 = ephemeral
    # (group, address) -> relay on?
    state: dict[tuple[int, int], bool] = field(default_factory=dict)
    # Sfeer: which (g,a) is active per room key (optional)
    sfeer_active: dict[str, tuple[int, int] | None] = field(default_factory=dict)
    sfeer_rooms: dict[tuple[int, int], str] = field(default_factory=dict)

    # Behaviour knobs (adversarial)
    drop_status_for: set[tuple[int, int]] = field(default_factory=set)
    status_delay: float = 0.0
    reply_delay: float = 0.0

    # Observability
    rx_log: list[BLXEvent] = field(default_factory=list)
    tx_log: list[BLXEvent] = field(default_factory=list)
    # Chronological blxmonitor-style lines (client-centric [SENT] / bare RX)
    bus_log: list[str] = field(default_factory=list)

    _server: asyncio.Server | None = field(default=None, repr=False)
    _writers: list[asyncio.StreamWriter] = field(default_factory=list, repr=False)
    _status_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _status_count: int = 0
    _custom_handler: OnCommand | None = field(default=None, repr=False)
    _bus_log_callback: BusLogCallback | None = field(default=None, repr=False)

    @property
    def bound_port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    def set_state(self, group: int, address: int, is_on: bool) -> None:
        self.state[(group, address)] = is_on

    def register_sfeer_mood(self, room: str, group: int, address: int) -> None:
        self.sfeer_rooms[(group, address)] = room
        self.sfeer_active.setdefault(room, None)

    def on_command(self, handler: OnCommand) -> None:
        """Optional override for custom adversarial behaviour."""
        self._custom_handler = handler

    def on_bus_log(self, callback: BusLogCallback | None) -> None:
        """Optional live callback for each human-readable bus line."""
        self._bus_log_callback = callback

    def _record_bus(self, line: str) -> None:
        self.bus_log.append(line)
        _BUS_LOGGER.info("%s", line)
        if self._bus_log_callback is not None:
            try:
                self._bus_log_callback(line)
            except Exception:
                pass

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        _LOGGER.debug("FakeGateway listening on %s:%s", self.host, self.bound_port)

    async def stop(self) -> None:
        for w in list(self._writers):
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def emit(self, command: str, group: int, address: int) -> None:
        """Push an unsolicited datagram to all connected clients."""
        data = encode_datagram(command, group, address)
        event = decode_datagram(data)
        self.tx_log.append(event)
        # Client-centric: gateway → client looks like a live bus event (no [SENT])
        self._record_bus(format_recv(event))
        for w in list(self._writers):
            try:
                w.write(data)
                await w.drain()
            except Exception:
                pass

    async def emit_sequence(
        self,
        events: list[tuple[str, int, int]],
        *,
        delay: float = 0.0,
    ) -> None:
        for i, (cmd, g, a) in enumerate(events):
            if delay and i:
                await asyncio.sleep(delay)
            await self.emit(cmd, g, a)

    async def emit_program_payload(
        self,
        payload: list[tuple[str, int, int]] | None = None,
        *,
        delay: float = 0.0,
    ) -> None:
        """Emit Program + exactly two following datagrams (programming payload).

        With ``skip_programming=True`` (library default) the client must drop
        all three frames. *payload* may look like a genuine Status reply
        (e.g. ``Set 2.80``) — that is intentional adversarial traffic.
        """
        if payload is None:
            payload = [("Data", 15, 82), ("Data", 4, 82)]
        if len(payload) != 2:
            raise ValueError("Program payload must be exactly 2 datagrams")
        await self.emit("Program", 0, 0)
        for i, (cmd, g, a) in enumerate(payload):
            if delay:
                await asyncio.sleep(delay)
            await self.emit(cmd, g, a)

    async def emit_light_sensor(
        self,
        *,
        select: tuple[int, int] = (1, 23),
        value: tuple[int, int] = (2, 145),
        delay: float = 0.0,
    ) -> None:
        """Emit a Select + Value pair as seen from real-bus light sensors.

        These may appear whenever light levels change and must not break
        framing or Status pairing in the client.
        """
        await self.emit("Select", select[0], select[1])
        if delay:
            await asyncio.sleep(delay)
        await self.emit("Value", value[0], value[1])

    async def wait_status_count(self, n: int, timeout: float = 5.0) -> None:
        """Wait until at least *n* Status commands have been received."""
        deadline = asyncio.get_event_loop().time() + timeout
        while self._status_count < n:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"only {self._status_count}/{n} Status received"
                )
            try:
                await asyncio.wait_for(self._status_event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"only {self._status_count}/{n} Status received"
                ) from None
            self._status_event.clear()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._writers.append(writer)
        try:
            while True:
                data = await reader.readexactly(2)
                event = decode_datagram(data)
                self.rx_log.append(event)
                # Client-centric: client → gateway is what blxmonitor labels [SENT]
                self._record_bus(format_sent(event))
                _LOGGER.debug("FakeGW RX %s", event)

                if self._custom_handler is not None:
                    result = self._custom_handler(self, event)
                    if asyncio.iscoroutine(result):
                        await result
                    continue

                await self._default_handle(event, writer)
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _default_handle(
        self, event: BLXEvent, writer: asyncio.StreamWriter
    ) -> None:
        key = (event.group, event.address)

        if event.command == "Status":
            self._status_count += 1
            self._status_event.set()
            if key in self.drop_status_for:
                return
            if self.status_delay:
                await asyncio.sleep(self.status_delay)
            is_on = self.state.get(key, False)
            reply = "Set" if is_on else "Reset"
            await self._send(writer, reply, event.group, event.address)
            return

        if self.reply_delay:
            await asyncio.sleep(self.reply_delay)

        if event.command == "Set":
            self.state[key] = True
            await self._sfeer_activate(writer, key)
            return
        if event.command == "Reset":
            self.state[key] = False
            return
        if event.command == "Toggle":
            self.state[key] = not self.state.get(key, False)
            # Echo resulting state as Set/Reset (many devices do)
            await self._send(
                writer,
                "Set" if self.state[key] else "Reset",
                event.group,
                event.address,
            )
            return
        if event.command == "Dimmer":
            # Sfeer-style: activate this address, reset other moods in same room
            await self._sfeer_activate(writer, key, force_on=True)
            return

    async def _sfeer_activate(
        self,
        writer: asyncio.StreamWriter,
        key: tuple[int, int],
        *,
        force_on: bool = False,
    ) -> None:
        room = self.sfeer_rooms.get(key)
        if room is not None:
            prev = self.sfeer_active.get(room)
            if prev is not None and prev != key:
                self.state[prev] = False
                await self._send(writer, "Reset", prev[0], prev[1])
            self.sfeer_active[room] = key
            self.state[key] = True
            await self._send(writer, "Set", key[0], key[1])
            return
        if force_on:
            self.state[key] = True
            await self._send(writer, "Set", key[0], key[1])

    async def _send(
        self, writer: asyncio.StreamWriter, command: str, group: int, address: int
    ) -> None:
        data = encode_datagram(command, group, address)
        event = decode_datagram(data)
        self.tx_log.append(event)
        self._record_bus(format_recv(event))
        writer.write(data)
        await writer.drain()
        _LOGGER.debug("FakeGW TX %s", event)
