"""Async B-Logicx connection library.

This module provides an asyncio-native client for the BL-NWM gateway.
It has no external dependencies beyond the Python standard library.

Important: the gateway is a single-slot TCP device, and each connection has
exactly one receive stream. This class enforces a process-wide singleton per
(host, port) and runs **one** background reader that fans events out to all
subscribers. Concurrent ``readexactly(2)`` loops on the same socket would
desynchronise the 2-byte framing and produce garbage group.address values
(and lost Status replies).
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from collections.abc import Callable
from typing import AsyncIterator

from .const import BLX_TCP_PORT, COMMAND_NAMES
from .models import BLXEvent
from .protocol import decode_datagram, encode_datagram

_LOGGER = logging.getLogger(__name__)

RawRxCallback = Callable[[bytes], None]


class BLXConnectionError(Exception):
    """Base exception for B-Logicx connection issues."""


class BLXConnection:
    """Async connection to a B-Logicx BL-NWM gateway.

    This class enforces a single connection per (host, port) at all times.
    Only one TCP connection to the gateway is ever allowed (gateway limitation).

    By default, "Program" commands (and the two datagrams that follow them)
    are automatically skipped. These datagrams carry programming payload
    rather than normal bus events. Normal listeners (such as the Home
    Assistant integration) should use the default.

    If the two payload datagrams do not arrive within ~10 seconds after a
    Program command, the skip state is automatically reset. This prevents
    the receiver from indefinitely discarding legitimate datagrams if the
    programming sequence was interrupted.

    Pass skip_programming=False to receive every raw datagram, including
    programming traffic. This is intended for diagnostic tools.
    """

    # Class-level registry: only one live instance per (host, port).
    _active_connections: dict[tuple[str, int], "BLXConnection"] = {}
    _connect_locks: dict[tuple[str, int], asyncio.Lock] = {}

    # Timeout after which we give up waiting for the 2 datagrams following a
    # "Program" command and resume normal processing.
    PROGRAM_PAYLOAD_TIMEOUT = 10.0  # seconds

    def __new__(cls, host: str, port: int = BLX_TCP_PORT, *, skip_programming: bool = True):
        key = (host, port)
        if key in cls._active_connections:
            existing = cls._active_connections[key]
            if not getattr(existing, "_closed", False):
                _LOGGER.debug("Reusing existing connection instance for %s:%s", host, port)
                return existing
            cls._active_connections.pop(key, None)
        instance = super().__new__(cls)
        cls._active_connections[key] = instance
        return instance

    def __init__(
        self, host: str, port: int = BLX_TCP_PORT, *, skip_programming: bool = True
    ) -> None:
        if getattr(self, "_initialized", False):
            # Singleton re-entry: allow enabling raw Program traffic if requested
            if not skip_programming:
                self._skip_programming = False
            return
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._closed = False
        self._skip_programming = skip_programming
        self._skip_count = 0
        self._skip_deadline = 0.0
        self._initialized = True

        # Single background reader → fan-out to subscribers (unbounded queues).
        self._recv_task: asyncio.Task | None = None
        self._subscribers: list[asyncio.Queue] = []
        self._start_lock: asyncio.Lock | None = None  # created lazily (needs running loop)
        # Raw RX tee (before Program-skip) for bus repeater
        self._raw_rx_callbacks: list[RawRxCallback] = []

    def _get_start_lock(self) -> asyncio.Lock:
        if self._start_lock is None:
            self._start_lock = asyncio.Lock()
        return self._start_lock

    async def connect(self) -> None:
        """Open the TCP connection. Guards against opening when already open."""
        if self._writer is not None and not getattr(self, "_closed", False):
            await self._ensure_receiver()
            return

        key = (self.host, self.port)
        lock = BLXConnection._connect_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if self._writer is not None and not getattr(self, "_closed", False):
                await self._ensure_receiver()
                return

            if self._writer is not None:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                self._writer = None
                self._reader = None

            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self.host, self.port
                )
                self._closed = False
                self._skip_count = 0
                self._skip_deadline = 0.0
                _LOGGER.debug("Connected to %s:%s", self.host, self.port)
            except Exception as exc:
                self._reader = None
                self._writer = None
                self._closed = True
                BLXConnection._active_connections.pop(key, None)
                raise BLXConnectionError(
                    f"Failed to connect to {self.host}:{self.port}"
                ) from exc

        await self._ensure_receiver()

    async def close(self) -> None:
        """Close the connection and release the singleton slot."""
        key = (self.host, self.port)
        lock = BLXConnection._connect_locks.setdefault(key, asyncio.Lock())
        async with lock:
            self._closed = True
            BLXConnection._active_connections.pop(key, None)

            # Wake event subscribers first
            for q in list(self._subscribers):
                try:
                    q.put_nowait(None)  # end-of-stream sentinel
                except Exception:
                    pass
            self._subscribers.clear()

            # Close the socket *before* awaiting the receiver task so that
            # readexactly() unblocks; cancelling alone can hang on some kernels.
            if self._writer is not None:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                self._writer = None
                self._reader = None
                _LOGGER.debug("Connection to %s closed", self.host)

            task = self._recv_task
            self._recv_task = None
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            BLXConnection._connect_locks.pop(key, None)

    async def __aenter__(self) -> BLXConnection:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _encode_datagram(self, command: str | int, group: int, address: int) -> bytes:
        """Build the 2-byte datagram."""
        return encode_datagram(command, group, address)

    def _decode_datagram(self, data: bytes) -> BLXEvent:
        """Decode a 2-byte datagram into a BLXEvent."""
        event = decode_datagram(data)
        _LOGGER.debug("RX %s (raw %02X %02X)", event, data[0], data[1])
        return event

    def register_raw_rx(self, callback: RawRxCallback) -> Callable[[], None]:
        """Register for every raw 2-byte RX datagram (before Program-skip)."""
        self._raw_rx_callbacks.append(callback)

        def _unreg() -> None:
            if callback in self._raw_rx_callbacks:
                self._raw_rx_callbacks.remove(callback)

        return _unreg

    async def send_raw(self, data: bytes) -> None:
        """Send exactly 2 raw bytes to the gateway."""
        if len(data) != 2:
            raise ValueError("datagram must be exactly 2 bytes")
        if self._writer is None:
            await self.connect()
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()

    async def send(self, command: str | int, group: int, address: int) -> None:
        """Send a command to the bus."""
        if self._writer is None:
            await self.connect()
        assert self._writer is not None
        datagram = self._encode_datagram(command, group, address)
        self._writer.write(datagram)
        await self._writer.drain()
        _LOGGER.debug(
            "TX %s %s.%s (raw %02X %02X)",
            command,
            group,
            address,
            datagram[0],
            datagram[1],
        )

    async def _read_exactly_two(self) -> bytes:
        """Read one framed 2-byte datagram from the socket (sole reader path)."""
        if self._reader is None:
            await self.connect()
        assert self._reader is not None
        try:
            data = await self._reader.readexactly(2)
        except asyncio.IncompleteReadError as exc:
            await self.close()
            raise BLXConnectionError("Connection closed while reading") from exc
        except (OSError, asyncio.CancelledError):
            await self.close()
            raise
        if not data:
            await self.close()
            raise BLXConnectionError("Connection closed by peer")
        return data

    async def receive(self) -> BLXEvent:
        """Receive the next event (Program-skip applied).

        Always goes through the shared subscriber stream so the socket is
        never read from two places at once.
        """
        async for event in self.events():
            return event
        raise BLXConnectionError("Connection closed")

    async def _ensure_receiver(self) -> None:
        """Start the single background reader if it is not already running."""
        async with self._get_start_lock():
            if self._closed:
                return
            if self._recv_task is not None and not self._recv_task.done():
                return
            if self._reader is None:
                return
            self._recv_task = asyncio.create_task(
                self._recv_loop(), name=f"blx_recv_{self.host}_{self.port}"
            )
            _LOGGER.debug("Started single BLX receiver task for %s:%s", self.host, self.port)

    async def _recv_loop(self) -> None:
        """Sole reader: decode datagrams and fan out to all subscribers."""
        try:
            while not self._closed:
                try:
                    data = await self._read_exactly_two()
                except (BLXConnectionError, asyncio.CancelledError):
                    break
                except Exception:
                    _LOGGER.exception("BLX receiver read failed")
                    break

                # Tee raw bytes before Program-skip so repeaters see programming traffic
                for cb in list(self._raw_rx_callbacks):
                    try:
                        cb(data)
                    except Exception:
                        _LOGGER.exception("Raw RX callback failed")

                event = self._decode_datagram(data)

                if self._skip_programming:
                    now = time.monotonic()
                    if self._skip_count > 0:
                        if now > self._skip_deadline:
                            _LOGGER.warning(
                                "Timed out waiting for Program payload datagrams "
                                "after %s seconds; resuming normal event processing "
                                "(raw %02X %02X → %s).",
                                BLXConnection.PROGRAM_PAYLOAD_TIMEOUT,
                                data[0],
                                data[1],
                                event,
                            )
                            self._skip_count = 0
                            # Fall through and deliver this event
                        else:
                            _LOGGER.debug(
                                "Skipping Program payload (%s left): %s raw %02X %02X",
                                self._skip_count,
                                event,
                                data[0],
                                data[1],
                            )
                            self._skip_count -= 1
                            continue

                    if event.command == "Program":
                        _LOGGER.debug(
                            "Program command received, will skip the next 2 datagrams"
                        )
                        self._skip_count = 2
                        self._skip_deadline = now + BLXConnection.PROGRAM_PAYLOAD_TIMEOUT
                        continue

                # Fan-out copy to every subscriber
                dead: list[asyncio.Queue] = []
                for q in list(self._subscribers):
                    try:
                        q.put_nowait(event)
                    except Exception:
                        dead.append(q)
                for q in dead:
                    if q in self._subscribers:
                        self._subscribers.remove(q)

        finally:
            # Unblock any waiting subscribers
            for q in list(self._subscribers):
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
            _LOGGER.debug("BLX receiver task ended for %s:%s", self.host, self.port)

    async def events(self) -> AsyncIterator[BLXEvent]:
        """Async iterator yielding events forever.

        Multiple concurrent consumers are safe: they all receive the same
        stream from the single background reader (no concurrent socket reads).

        When skip_programming is True (the default), Program commands and the
        two following payload datagrams are suppressed.
        """
        if self._writer is None or self._closed:
            await self.connect()
        else:
            await self._ensure_receiver()

        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    @asynccontextmanager
    async def monitor(self) -> AsyncIterator[asyncio.Queue[BLXEvent]]:
        """Context manager that feeds events into a queue.

        Useful when you also want to send commands while receiving.
        """
        queue: asyncio.Queue[BLXEvent] = asyncio.Queue()
        receiver_task = asyncio.create_task(self._feed_queue(queue))

        try:
            yield queue
        finally:
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass

    async def _feed_queue(self, queue: asyncio.Queue[BLXEvent]) -> None:
        try:
            async for event in self.events():
                await queue.put(event)
        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("Event feeder stopped")
