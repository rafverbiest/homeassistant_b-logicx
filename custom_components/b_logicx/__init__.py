"""B-Logicx integration for Home Assistant.

This integration uses the shared `b_logicx` library for communication
with the BL-NWM gateway.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.device_registry as dr

from .const import (
    ADDRESS_TYPE_EXU,
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_NORMAL,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_HOST,
    CONF_PORT,
    DEFAULT_CLOSE_TIME,
    DEFAULT_OFF_COMMAND,
    DEFAULT_ON_COMMAND,
    DEFAULT_OPEN_TIME,
    DEFAULT_PORT,
    DOMAIN,
    get_cover_device_identifiers,
    get_device_identifiers,
    get_ldm_device_identifiers,
    get_rtc_device_identifiers,
    get_sfeer_device_identifiers,
    get_tsm_device_identifiers,
)
from .hub import BLogicxHub
from .rtc_sync import RtcSyncManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.COVER,
    Platform.SELECT,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]


def _merge_legacy_shutter_pairs(addresses: list[dict]) -> list[dict]:
    """Convert legacy two-entry shutter pairs into one cover entry each.

    Legacy format (partial 0.5): two dicts with type=shutter, role=open|close,
    and sibling_* mutual references. New format: one dict with open_*/close_*.
    """
    result: list[dict] = []
    consumed: set[tuple[int, int]] = set()

    # Index role=open entries for pairing
    opens: dict[tuple[int, int], dict] = {}
    closes: dict[tuple[int, int], dict] = {}
    for addr in addresses:
        if addr.get("type") != ADDRESS_TYPE_SHUTTER:
            continue
        # Already new format
        if "open_group" in addr and "close_group" in addr and "role" not in addr:
            continue
        role = addr.get("role")
        key = (int(addr["group"]), int(addr["address"]))
        if role == "open":
            opens[key] = addr
        elif role == "close":
            closes[key] = addr

    for addr in addresses:
        # Pass through normal and already-new shutter entries
        if addr.get("type") != ADDRESS_TYPE_SHUTTER:
            result.append(addr)
            continue
        if "open_group" in addr and "close_group" in addr and "role" not in addr:
            result.append(addr)
            continue

        role = addr.get("role")
        key = (int(addr["group"]), int(addr["address"]))
        if key in consumed:
            continue

        if role == "open":
            sib = (
                int(addr.get("sibling_group", 0)),
                int(addr.get("sibling_address", 0)),
            )
            close_addr = closes.get(sib)
            name = (
                addr.get("shutter_name")
                or (close_addr or {}).get("shutter_name")
                or addr.get("name")
                or "Cover"
            )
            # Strip role suffix from name if present
            if name.endswith(" (Open)"):
                name = name[: -len(" (Open)")]
            result.append(
                {
                    "name": name,
                    "type": ADDRESS_TYPE_SHUTTER,
                    "open_group": key[0],
                    "open_address": key[1],
                    "close_group": sib[0],
                    "close_address": sib[1],
                    "open_time": DEFAULT_OPEN_TIME,
                    "close_time": DEFAULT_CLOSE_TIME,
                    "check_status": addr.get("check_status", False)
                    or (close_addr or {}).get("check_status", False),
                }
            )
            consumed.add(key)
            if sib in closes:
                consumed.add(sib)
        elif role == "close":
            # Only emit if we never saw the matching open (orphan close)
            sib = (
                int(addr.get("sibling_group", 0)),
                int(addr.get("sibling_address", 0)),
            )
            if sib in opens:
                # Will be handled when we process open
                continue
            name = addr.get("shutter_name") or addr.get("name") or "Cover"
            if name.endswith(" (Close)"):
                name = name[: -len(" (Close)")]
            result.append(
                {
                    "name": name,
                    "type": ADDRESS_TYPE_SHUTTER,
                    "open_group": sib[0],
                    "open_address": sib[1],
                    "close_group": key[0],
                    "close_address": key[1],
                    "open_time": DEFAULT_OPEN_TIME,
                    "close_time": DEFAULT_CLOSE_TIME,
                    "check_status": addr.get("check_status", False),
                }
            )
            consumed.add(key)
        else:
            # Unknown shutter shape — drop rather than create broken entities
            _LOGGER.warning(
                "Dropping unrecognised shutter entry during migration: %s", addr
            )

    return result


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry data formats to the current version.

    Home Assistant calls this automatically when it loads a ConfigEntry
    whose stored version is lower than the VERSION declared in the
    ConfigFlow (currently 4).
    """
    _LOGGER.debug(
        "Checking B-Logicx config entry migration (current version=%s)",
        config_entry.version,
    )

    version = config_entry.version
    new_data = {**config_entry.data}
    addresses = list(new_data.get(CONF_ADDRESSES, []))

    if version < 2:
        for addr in addresses:
            addr.pop("area", None)
            addr.pop("control_mode", None)
            addr.setdefault("type", ADDRESS_TYPE_NORMAL)
            addr.setdefault("on_command", DEFAULT_ON_COMMAND)
            addr.setdefault("off_command", DEFAULT_OFF_COMMAND)
            addr.setdefault("check_status", False)
        new_data[CONF_ADDRESSES] = addresses
        version = 2
        _LOGGER.info("Migrated B-Logicx config entry fields for v2")

    if version < 3:
        # Merge legacy two-entry shutter pairs into single CoverEntity configs
        addresses = list(new_data.get(CONF_ADDRESSES, []))
        for addr in addresses:
            if addr.get("type") != ADDRESS_TYPE_SHUTTER:
                addr.setdefault("type", ADDRESS_TYPE_NORMAL)
                addr.setdefault("on_command", DEFAULT_ON_COMMAND)
                addr.setdefault("off_command", DEFAULT_OFF_COMMAND)
        addresses = _merge_legacy_shutter_pairs(addresses)
        for addr in addresses:
            if addr.get("type") == ADDRESS_TYPE_SHUTTER:
                addr.setdefault("check_status", False)
                for k in (
                    "role",
                    "shutter_name",
                    "sibling_group",
                    "sibling_address",
                    "sibling_on_command",
                    "sibling_off_command",
                    "group",
                    "address",
                    "on_command",
                    "off_command",
                    "open_command",
                    "close_command",
                    "opposite_command",
                ):
                    addr.pop(k, None)
        new_data[CONF_ADDRESSES] = addresses
        version = 3
        _LOGGER.info(
            "Migrated B-Logicx config entry to v3 (CoverEntity single-entry covers)"
        )

    if version < 4:
        # v0.5.1: per-cover travel times for HA open/closed estimate
        addresses = list(new_data.get(CONF_ADDRESSES, []))
        for addr in addresses:
            if addr.get("type") != ADDRESS_TYPE_SHUTTER:
                continue
            for k in ("open_command", "close_command", "opposite_command"):
                addr.pop(k, None)
            addr.setdefault("open_time", DEFAULT_OPEN_TIME)
            addr.setdefault("close_time", DEFAULT_CLOSE_TIME)
        new_data[CONF_ADDRESSES] = addresses
        version = 4
        _LOGGER.info(
            "Migrated B-Logicx config entry to v4 (cover open_time/close_time)"
        )

    if version != config_entry.version or new_data != dict(config_entry.data):
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=version,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up B-Logicx from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    if entry.entry_id in hass.data[DOMAIN]:
        hub: BLogicxHub = hass.data[DOMAIN][entry.entry_id]
    else:
        hub = BLogicxHub(hass, host, port)
        hass.data[DOMAIN][entry.entry_id] = hub

    try:
        await hub.async_start()
    except Exception as err:
        _LOGGER.error("Failed to connect to B-Logicx gateway at %s: %s", host, err)
        raise ConfigEntryNotReady(f"Could not connect to {host}") from err

    async def _close_on_ha_stop(_event) -> None:
        await hub.async_close()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _close_on_ha_stop)
    )

    device_registry = dr.async_get(hass)
    addresses = entry.data.get(CONF_ADDRESSES, [])
    host = entry.data[CONF_HOST]
    n_normal = sum(
        1
        for a in addresses
        if a.get("type", ADDRESS_TYPE_NORMAL) == ADDRESS_TYPE_NORMAL
    )
    n_cover = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_SHUTTER)
    n_sfeer = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_SFEER)
    n_exu = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_EXU)
    n_rtc = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_RTC)
    n_ldm = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_LDM)
    n_tsm = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_TSM)
    _LOGGER.info(
        "Setting up B-Logicx with %d entries "
        "(%d normal, %d cover, %d sfeer, %d exu, %d rtc, %d ldm, %d tsm)",
        len(addresses),
        n_normal,
        n_cover,
        n_sfeer,
        n_exu,
        n_rtc,
        n_ldm,
        n_tsm,
    )

    for addr in addresses:
        if addr.get("type") == ADDRESS_TYPE_SHUTTER:
            identifiers = get_cover_device_identifiers(
                host,
                int(addr["open_group"]),
                int(addr["open_address"]),
                int(addr["close_group"]),
                int(addr["close_address"]),
            )
            name = addr.get("name", "Cover")
            model = (
                f"Cover {addr['open_group']}.{addr['open_address']} / "
                f"{addr['close_group']}.{addr['close_address']}"
            )
        elif addr.get("type") == ADDRESS_TYPE_SFEER:
            name = addr.get("name", "Sfeer")
            identifiers = get_sfeer_device_identifiers(host, name)
            n_moods = len(addr.get("moods") or [])
            model = f"Sfeer room ({n_moods} moods)"
        elif addr.get("type") == ADDRESS_TYPE_EXU:
            identifiers = get_device_identifiers(
                host, addr["group"], addr["address"]
            )
            name = addr.get("name", f"EXU {addr['group']}.{addr['address']}")
            model = f"EXU {addr['group']}.{addr['address']}"
        elif addr.get("type") == ADDRESS_TYPE_RTC:
            identifiers = get_rtc_device_identifiers(
                host, int(addr["group"]), int(addr["address"])
            )
            name = addr.get("name", f"RTC {addr['group']}.{addr['address']}")
            model = f"RTC {addr['group']}.{addr['address']}"
        elif addr.get("type") == ADDRESS_TYPE_LDM:
            identifiers = get_ldm_device_identifiers(
                host, int(addr["group"]), int(addr["address"])
            )
            name = addr.get("name", f"LDM {addr['group']}.{addr['address']}")
            model = f"LDM {addr['group']}.{addr['address']}"
        elif addr.get("type") == ADDRESS_TYPE_TSM:
            identifiers = get_tsm_device_identifiers(
                host, int(addr["group"]), int(addr["address"])
            )
            name = addr.get("name", f"TSM {addr['group']}.{addr['address']}")
            model = f"TSM {addr['group']}.{addr['address']}"
        else:
            identifiers = get_device_identifiers(
                host, addr["group"], addr["address"]
            )
            name = addr.get("name", f"{addr['group']}.{addr['address']}")
            model = f"Bus Device {addr['group']}.{addr['address']}"

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=identifiers,
            name=name,
            manufacturer="B-Logicx",
            model=model,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # RTC: after platforms (Status probes) have started, run startup sync + timers
    rtc_manager = RtcSyncManager.from_addresses(hass, hub, addresses)
    if rtc_manager is not None:
        hass.data[DOMAIN][f"{entry.entry_id}_rtc"] = rtc_manager

        async def _start_rtc(_event=None) -> None:
            await rtc_manager.async_start()

        entry.async_on_unload(
            hass.bus.async_listen_once("homeassistant_started", _start_rtc)
        )
        # If HA is already running (reload), start immediately in background
        if hass.is_running:
            entry.async_create_background_task(
                hass, rtc_manager.async_start(), name="b_logicx_rtc_start"
            )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    We only stop the listener here. The underlying connection is kept alive
    (via the singleton in the library) so that a subsequent reload does not
    attempt to open a second TCP connection to the gateway.
    """
    rtc_key = f"{entry.entry_id}_rtc"
    rtc_manager = hass.data[DOMAIN].pop(rtc_key, None)
    if rtc_manager is not None:
        await rtc_manager.async_stop()

    hub: BLogicxHub = hass.data[DOMAIN].pop(entry.entry_id)
    await hub.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
