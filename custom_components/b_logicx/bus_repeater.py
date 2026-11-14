"""Share the one gateway connection with BLConfig or blxmonitor.

Home Assistant already holds the gateway socket. This server listens on all
interfaces, on the same port as the gateway by default. Loopback is always
allowed. Any other client must be inside the configured CIDR, or, when that
is empty, on the gateway's /24.

Bytes from the gateway are copied to every client before Program filtering.
Bytes from a client are two-byte frames written to the gateway under the
same request lock as Status and the sensors, so they do not land in the
middle of those sequences.

While that TCP port is open, this also answers the NWM search on UDP 30718.
The setup reply names this listen port and no second port. The firmware
query is answered with the MAC A5-51-57-10-00-00 and the first digits of
the manifest version. Read as letters (5=S, 1=I, 7=T, 0=O) that MAC spells
ASSISTIO.
The allow-list is unchanged: a machine that can see the search can still
be refused on TCP.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import TYPE_CHECKING

try:
    from .b_logicx.discover import DISCOVER_PORT, reply_to_discover
except ImportError:  # offline tests import this file as a top-level module
    from b_logicx.discover import DISCOVER_PORT, reply_to_discover

if TYPE_CHECKING:
    from .b_logicx.connection import BLXConnection

try:
    from .const import DEFAULT_BUS_REPEATER_PORT
except ImportError:  # offline tests with flat sys.path
    from const import DEFAULT_BUS_REPEATER_PORT

_LOGGER = logging.getLogger(__name__)


def suggested_repeater_cidr(gateway_host: str) -> str:
    """Suggest a /24 from an IPv4 gateway address. Empty if host is not an IPv4."""
    try:
        ip = ipaddress.ip_address(gateway_host)
    except ValueError:
        return ""
    if ip.version != 4:
        return ""
    return str(ipaddress.ip_network(f"{ip}/24", strict=False))


def _legacy_gateway_slash24(client: ipaddress.IPv4Address | ipaddress.IPv6Address, gateway_ip: str) -> bool:
    """Old behaviour: client is on the gateway's /24 (IPv4 only)."""
    try:
        gateway = ipaddress.ip_address(gateway_ip)
    except ValueError:
        return False
    if gateway.version != 4 or client.version != 4:
        return False
    return client in ipaddress.ip_network(f"{gateway}/24", strict=False)


def client_allowed(
    client_ip: str,
    gateway_ip: str,
    allow_cidr: str | None = None,
) -> bool:
    """Return True if this repeater client may connect.

    Loopback is always allowed. If *allow_cidr* is set, the client must be
    inside that network. If it is empty, fall back to the gateway /24.
    """
    try:
        client = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if client.is_loopback:
        return True
    text = (allow_cidr or "").strip()
    if text:
        try:
            network = ipaddress.ip_network(text, strict=False)
        except ValueError:
            return False
        return client in network
    return _legacy_gateway_slash24(client, gateway_ip)


class BusRepeater:
    """asyncio TCP server that relays 2-byte B-Logicx datagrams."""

    def __init__(
        self,
        conn: BLXConnection,
        gateway_host: str,
        *,
        port: int = DEFAULT_BUS_REPEATER_PORT,
        allow_cidr: str | None = None,
        request_lock: asyncio.Lock | None = None,
    ) -> None:
        self._conn = conn
        self._gateway_host = gateway_host
        self._port = port
        self._allow_cidr = (allow_cidr or "").strip() or None
        self._request_lock = request_lock
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.StreamWriter] = []
        self._unsub_raw = None
        self._announce_sock: socket.socket | None = None
        self._announce_task: asyncio.Task | None = None

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
        """Listen, and copy every raw gateway frame to connected clients."""
        if self._server is not None:
            return

        def _on_raw(data: bytes) -> None:
            self._broadcast(data)

        self._unsub_raw = self._conn.register_raw_rx(_on_raw)
        self._server = await asyncio.start_server(
            self._handle_client, "0.0.0.0", self._port
        )
        _LOGGER.info(
            "Bus repeater listening on 0.0.0.0:%s (NWM subnet filter vs %s)",
            self._port,
            self._gateway_host,
        )
        await self._start_announce()

    async def stop(self) -> None:
        await self._stop_announce()
        if self._unsub_raw is not None:
            self._unsub_raw()
            self._unsub_raw = None
        for w in list(self._clients):
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            _LOGGER.info("Bus repeater stopped")

    async def _start_announce(self) -> None:
        """Answer the NWM search on UDP 30718. A busy port leaves TCP running."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            sock.bind(("0.0.0.0", DISCOVER_PORT))
        except OSError:
            _LOGGER.warning(
                "Bus repeater could not listen for an NWM search on UDP %s",
                DISCOVER_PORT,
            )
            sock.close()
            return
        self._announce_sock = sock
        self._announce_task = asyncio.create_task(self._announce_loop())
        _LOGGER.info("Bus repeater answering an NWM search on UDP %s", DISCOVER_PORT)

    async def _stop_announce(self) -> None:
        task = self._announce_task
        self._announce_task = None
        sock = self._announce_sock
        self._announce_sock = None
        if sock is not None:
            sock.close()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _announce_loop(self) -> None:
        sock = self._announce_sock
        if sock is None:
            return
        loop = asyncio.get_running_loop()
        try:
            while True:
                data, addr = await loop.sock_recvfrom(sock, 512)
                reply = reply_to_discover(data, self._port)
                if reply is None:
                    continue
                try:
                    await loop.sock_sendto(sock, reply, addr)
                except OSError:
                    _LOGGER.debug("Discovery reply to %s failed", addr, exc_info=True)
        except OSError:
            return

    def _broadcast(self, data: bytes) -> None:
        """Write one received frame to every client without blocking the reader."""
        dead: list[asyncio.StreamWriter] = []
        for w in list(self._clients):
            try:
                w.write(data)
                # schedule drain without blocking the NWM reader
                asyncio.create_task(self._drain(w, dead))
            except Exception:
                dead.append(w)
        for w in dead:
            if w in self._clients:
                self._clients.remove(w)

    async def _drain(
        self, writer: asyncio.StreamWriter, dead: list[asyncio.StreamWriter]
    ) -> None:
        try:
            await writer.drain()
        except Exception:
            if writer in self._clients:
                self._clients.remove(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Accept one client, or close it when the allow list says no.

        Each read is exactly two bytes, one datagram, then written to the gateway.
        """
        peer = writer.get_extra_info("peername")
        client_ip = peer[0] if peer else ""
        if not client_allowed(client_ip, self._gateway_host, self._allow_cidr):
            _LOGGER.warning(
                "Bus repeater rejected client %s (allowed: %s, gateway %s)",
                client_ip,
                self._allow_cidr or "gateway /24",
                self._gateway_host,
            )
            writer.close()
            await writer.wait_closed()
            return

        _LOGGER.info("Bus repeater client connected: %s", peer)
        self._clients.append(writer)
        try:
            while True:
                data = await reader.readexactly(2)
                if self._request_lock is not None:
                    async with self._request_lock:
                        await self._conn.send_raw(data)
                else:
                    await self._conn.send_raw(data)
        except (asyncio.IncompleteReadError, ConnectionResetError, ConnectionError):
            pass
        finally:
            if writer in self._clients:
                self._clients.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            _LOGGER.info("Bus repeater client disconnected: %s", peer)
