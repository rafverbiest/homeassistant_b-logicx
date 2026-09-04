"""TCP bus repeater — share the single NWM connection with BLConfig / blxmonitor.

Listens on HA (default port 10001). Accepts clients on the same subnet as the
configured NWM. Forwards raw 2-byte RX from the gateway (pre Program-skip) and
forwards complete 2-byte client TX to the gateway.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .b_logicx.connection import BLXConnection

_LOGGER = logging.getLogger(__name__)


def _same_subnet(client_ip: str, gateway_ip: str) -> bool:
    """Return True if client and gateway share a common interface subnet on this host."""
    try:
        client = ipaddress.ip_address(client_ip)
        gateway = ipaddress.ip_address(gateway_ip)
    except ValueError:
        return False

    # Enumerate local interfaces; require client and gateway in same network
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            pass
    except OSError:
        pass

    # Prefer: find a local address that shares a /24 with the gateway, then
    # require the client on that same /24. Fallback: same /24 as gateway alone.
    gw_net = ipaddress.ip_network(f"{gateway}/24", strict=False)
    if client not in gw_net:
        return False

    # Also verify we have a local IP on that subnet (HA is on the LAN)
    try:
        hostname = socket.gethostname()
        for res in socket.getaddrinfo(hostname, None, socket.AF_INET):
            local = ipaddress.ip_address(res[4][0])
            if local in gw_net:
                return True
    except OSError:
        pass

    # Fallback: allow if client is in gateway /24 (typical HA on same LAN)
    return client in gw_net


class BusRepeater:
    """asyncio TCP server that relays 2-byte B-Logicx datagrams."""

    def __init__(
        self,
        conn: BLXConnection,
        gateway_host: str,
        *,
        port: int = 10001,
        request_lock: asyncio.Lock | None = None,
    ) -> None:
        self._conn = conn
        self._gateway_host = gateway_host
        self._port = port
        self._request_lock = request_lock
        self._server: asyncio.Server | None = None
        self._clients: list[asyncio.StreamWriter] = []
        self._unsub_raw = None

    @property
    def port(self) -> int:
        return self._port

    async def start(self) -> None:
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

    async def stop(self) -> None:
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

    def _broadcast(self, data: bytes) -> None:
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
        peer = writer.get_extra_info("peername")
        client_ip = peer[0] if peer else ""
        if not _same_subnet(client_ip, self._gateway_host):
            _LOGGER.warning(
                "Bus repeater rejected client %s (not on NWM subnet of %s)",
                client_ip,
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
