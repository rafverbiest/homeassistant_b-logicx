"""Start and stop one B-Logicx config entry.

async_setup_entry:

1. Register the YAML download route.
2. Open the hub, or reuse the one already stored for this entry.
3. Turn on SoftM tracking and the bus repeater when those options say so.
4. Create one device per address, drop devices whose address was removed,
   and load the entity platforms.
5. Start the clock sync after the platforms, so startup Status probes go first.

A reload stops the listener and leaves the TCP socket open, so it does not
open a second connection. The socket closes when Home Assistant itself stops.
Without this, connection errors would appear on reload, since
BL-NWM has just a single slot available.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.device_registry as dr

from .b_logicx.softm_tracker import SoftMConfig
from .const import *
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
    Platform.MEDIA_PLAYER,
]



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Connect, register devices, and load every platform for this entry."""
    hass.data.setdefault(DOMAIN, {})

    from .yaml_download import async_setup_yaml_downloads

    async_setup_yaml_downloads(hass)

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
    # This is the master switch for the Virtual Status Module.
    # Each address still needs enable_softm_status_tracking before is_softm_address is true.
    softm_on = bool(entry.options.get(CONF_SOFTM_TRACKING_ENABLED, False))
    softm_cfgs: list[SoftMConfig] = []
    if softm_on:
        for a in entry.data.get(CONF_ADDRESSES, []):
            if not is_softm_address(a):
                continue
            timer = a.get("softm_timer")
            softm_cfgs.append(
                SoftMConfig(
                    group=int(a["group"]),
                    address=int(a["address"]),
                    timer_seconds=float(timer) if timer not in (None, "", 0) else None,
                    persist=bool(a.get("persist_state", True)),
                    default_state=bool(a.get("default_state", False)),
                )
            )
    hub.configure_softm_tracking(softm_on, softm_cfgs)
    if softm_on and softm_cfgs:
        _LOGGER.info(
            "SoftM status tracking enabled for %d address(es)", len(softm_cfgs)
        )

    # Optional. A failure to bind the listen port is logged and setup continues.
    if entry.options.get(CONF_BUS_REPEATER_ENABLED, False):
        rport = int(
            entry.options.get(CONF_BUS_REPEATER_PORT, DEFAULT_BUS_REPEATER_PORT)
        )
        allow = entry.options.get(CONF_BUS_REPEATER_ALLOW) or None
        try:
            await hub.async_start_repeater(port=rport, allow_cidr=allow)
        except OSError as err:
            _LOGGER.error("Bus repeater failed to start on port %s: %s", rport, err)

    # Reload only stops the listener. A full Home Assistant stop closes the socket.
    async def _close_on_ha_stop(_event) -> None:
        await hub.async_close()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _close_on_ha_stop)
    )

    async def _options_updated(_hass: HomeAssistant, updated: ConfigEntry) -> None:
        await _hass.config_entries.async_reload(updated.entry_id)

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    device_registry = dr.async_get(hass)
    addresses = entry.data.get(CONF_ADDRESSES, [])
    host = entry.data[CONF_HOST]
    n_switch = sum(1 for a in addresses if is_switch_address(a))
    n_aud = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_AUD)
    n_cover = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_SHUTTER)
    n_sfeer = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_SFEER)
    n_readonly = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_READONLY)
    n_rtc = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_RTC)
    n_ldm = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_LDM)
    n_tsm = sum(1 for a in addresses if a.get("type") == ADDRESS_TYPE_TSM)
    _LOGGER.info(
        "Setting up B-Logicx with %d entries "
        "(%d switch, %d cover, %d sfeer, %d readonly, %d rtc, %d ldm, %d tsm, %d aud)",
        len(addresses),
        n_switch,
        n_cover,
        n_sfeer,
        n_readonly,
        n_rtc,
        n_ldm,
        n_tsm,
        n_aud,
    )

    keep = configured_device_identifiers(host, addresses)
    for addr in addresses:
        identifiers, name, model = address_device(host, addr)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=identifiers,
            name=name,
            manufacturer="B-Logicx",
            model=model,
        )

    # An address removed in the options flow stays in the device registry
    # until this link is dropped. Home Assistant does not expire it.
    removed = 0
    for device in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if device_no_longer_configured(set(device.identifiers), keep):
            device_registry.async_remove_device(device.id)
            removed += 1
    if removed:
        _LOGGER.info(
            "Removed %d device(s) no longer in the address list", removed
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # After the platforms, so their startup Status probes are already queued.
    # A reload finds Home Assistant already running and starts the clock now.
    # A boot waits for homeassistant_started.
    rtc_manager = RtcSyncManager.from_addresses(hass, hub, addresses)
    if rtc_manager is not None:
        hass.data[DOMAIN][f"{entry.entry_id}_rtc"] = rtc_manager

        async def _start_rtc(_event=None) -> None:
            await rtc_manager.async_start()

        entry.async_on_unload(
            hass.bus.async_listen_once("homeassistant_started", _start_rtc)
        )
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


async def async_remove_config_entry_device(
    _hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow deleting a device whose address is no longer configured."""
    host = config_entry.data[CONF_HOST]
    keep = configured_device_identifiers(
        host, config_entry.data.get(CONF_ADDRESSES, [])
    )
    return device_no_longer_configured(set(device_entry.identifiers), keep)
