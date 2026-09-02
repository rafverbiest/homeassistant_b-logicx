"""RTC scheduling: startup (after Status), interval phase, DST watch."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from .b_logicx.rtc import build_rtc_sync_frames, next_phased_sync
from .const import (
    ADDRESS_TYPE_RTC,
    CONF_ADDRESSES,
    DEFAULT_RTC_DST_DELAY_MINUTES,
    DEFAULT_RTC_SYNC_INTERVAL_HOURS,
    DEFAULT_RTC_SYNC_MINUTE,
    DEFAULT_RTC_SYNC_ON_DST,
    DEFAULT_RTC_SYNC_ON_STARTUP,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .hub import BLogicxHub

_LOGGER = logging.getLogger(__name__)


def _tz(hass: HomeAssistant) -> ZoneInfo | timezone:
    name = getattr(hass.config, "time_zone", None) or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return timezone.utc


def _local_now(hass: HomeAssistant) -> datetime:
    return datetime.now(_tz(hass))


class RtcSyncManager:
    """Owns background tasks for one config entry's RTC modules."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: BLogicxHub,
        rtc_configs: list[dict[str, Any]],
    ) -> None:
        self.hass = hass
        self.hub = hub
        self.configs = list(rtc_configs)
        self._tasks: list[asyncio.Task] = []
        self._stopped = False
        self._started = False

    @classmethod
    def from_addresses(
        cls, hass: HomeAssistant, hub: BLogicxHub, addresses: list[dict]
    ) -> RtcSyncManager | None:
        rtcs = [a for a in addresses if a.get("type") == ADDRESS_TYPE_RTC]
        if not rtcs:
            return None
        return cls(hass, hub, rtcs)

    async def async_start(self) -> None:
        """Wait for Status quiet, optional startup sync, then interval + DST."""
        if self._started or self._stopped or not self.configs:
            return
        self._started = True
        try:
            await self.hub.async_wait_until_status_idle(quiet_for=0.5, timeout=60.0)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("RTC wait for Status idle failed")

        if self._stopped:
            return

        for cfg in self.configs:
            if cfg.get("sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP):
                await self.async_sync_one(cfg, reason="startup")

        for cfg in self.configs:
            self._tasks.append(
                self.hass.async_create_background_task(
                    self._interval_loop(cfg),
                    name=f"b_logicx_rtc_interval_{cfg.get('group')}_{cfg.get('address')}",
                )
            )
            if cfg.get("sync_on_dst", DEFAULT_RTC_SYNC_ON_DST):
                self._tasks.append(
                    self.hass.async_create_background_task(
                        self._dst_loop(cfg),
                        name=f"b_logicx_rtc_dst_{cfg.get('group')}_{cfg.get('address')}",
                    )
                )

    async def async_stop(self) -> None:
        self._stopped = True
        for t in self._tasks:
            if not t.done():
                t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                pass
        self._tasks.clear()

    async def async_sync_one(self, cfg: dict[str, Any], *, reason: str) -> None:
        if self._stopped:
            return
        group = int(cfg["group"])
        address = int(cfg["address"])
        name = cfg.get("name", f"RTC {group}.{address}")
        when = _local_now(self.hass)
        # Use naive local components for packing (hour/minute as wall clock)
        wall = when.replace(tzinfo=None) if when.tzinfo else when
        frames = build_rtc_sync_frames(wall, group, address)
        _LOGGER.info(
            "Synchronizing RTC %s (%s.%s) to %s (reason=%s)",
            name,
            group,
            address,
            wall.strftime("%Y-%m-%d %H:%M:%S"),
            reason,
        )
        try:
            await self.hub.async_send_sequence(frames, inter_frame_delay=0.01)
        except Exception:
            _LOGGER.exception("RTC sync failed for %s.%s", group, address)
            return
        self.hub.notify_rtc_synced(group, address, when)
        _LOGGER.info("RTC %s.%s sync complete", group, address)

    async def async_sync_all(self, *, reason: str = "manual") -> None:
        for cfg in self.configs:
            await self.async_sync_one(cfg, reason=reason)

    async def async_sync_key(self, group: int, address: int, *, reason: str) -> None:
        for cfg in self.configs:
            if int(cfg["group"]) == group and int(cfg["address"]) == address:
                await self.async_sync_one(cfg, reason=reason)
                return
        _LOGGER.warning("No RTC config for %s.%s", group, address)

    async def _interval_loop(self, cfg: dict[str, Any]) -> None:
        interval = float(
            cfg.get("sync_interval_hours", DEFAULT_RTC_SYNC_INTERVAL_HOURS)
        )
        minute = int(cfg.get("sync_minute", DEFAULT_RTC_SYNC_MINUTE))
        while not self._stopped:
            now = _local_now(self.hass)
            # next_phased_sync expects naive or aware consistently — use local naive
            wall = now.replace(tzinfo=None) if now.tzinfo else now
            nxt = next_phased_sync(wall, interval_hours=interval, sync_minute=minute)
            delay = (nxt - wall).total_seconds()
            if delay < 1:
                delay = 1
            _LOGGER.debug(
                "RTC %s.%s next interval sync at %s (in %.0fs)",
                cfg.get("group"),
                cfg.get("address"),
                nxt.isoformat(sep=" ", timespec="minutes"),
                delay,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            if self._stopped:
                return
            await self.async_sync_one(cfg, reason="interval")

    async def _dst_loop(self, cfg: dict[str, Any]) -> None:
        delay_min = int(
            cfg.get("dst_delay_minutes", DEFAULT_RTC_DST_DELAY_MINUTES)
        )
        last_offset = _local_now(self.hass).utcoffset()
        while not self._stopped:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                raise
            if self._stopped:
                return
            now = _local_now(self.hass)
            offset = now.utcoffset()
            if offset != last_offset:
                _LOGGER.info(
                    "DST offset change detected (%s → %s); RTC sync in %s min",
                    last_offset,
                    offset,
                    delay_min,
                )
                last_offset = offset
                try:
                    await asyncio.sleep(max(0, delay_min) * 60)
                except asyncio.CancelledError:
                    raise
                if self._stopped:
                    return
                await self.async_sync_one(cfg, reason="dst")
