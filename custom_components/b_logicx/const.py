"""Names and defaults for one configured bus address.

An address is a dict stored on the config entry. type decides which Home
Assistant entity it becomes. group and address, or a shutter's open and close
pair, or a Sfeer room's moods, say where it sits on the bus. The helpers at
the bottom build a stable entity id from the gateway host plus that location,
so a reload or a re-import keeps the same entity.
"""

DOMAIN = "b_logicx"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ADDRESSES = "addresses"

# Entry options (integration-level)
CONF_SOFTM_TRACKING_ENABLED = "softm_tracking_enabled"
CONF_BUS_REPEATER_ENABLED = "bus_repeater_enabled"
CONF_BUS_REPEATER_PORT = "bus_repeater_port"
CONF_BUS_REPEATER_ALLOW = "bus_repeater_allow"

# Gateway port and the repeater's listen port share the library constant.
try:
    from .b_logicx.const import BLX_TCP_PORT
except ImportError:  # offline tests with flat sys.path
    from b_logicx.const import BLX_TCP_PORT

DEFAULT_PORT = BLX_TCP_PORT
DEFAULT_BUS_REPEATER_PORT = BLX_TCP_PORT

# Address / entity types
ADDRESS_TYPE_RLM = "rlm"
ADDRESS_TYPE_SOFTM = "softm"
ADDRESS_TYPE_AUD = "aud"
ADDRESS_TYPE_SHUTTER = "shutter"
ADDRESS_TYPE_SFEER = "sfeer"
ADDRESS_TYPE_READONLY = "readonly"
ADDRESS_TYPE_RTC = "rtc"
ADDRESS_TYPE_LDM = "ldm"
ADDRESS_TYPE_TSM = "tsm"

# LDM / TSM defaults (listen / request sensors)
DEFAULT_LDM_GROUP = 1
DEFAULT_TSM_GROUP = 1

TSM_PRESET_LABELS = ("Night", "Day", "Away", "Holiday")

# Sfeer (room moods) defaults — B-Logicx convention; user may override
# One room = one bus group (typically 5, then 6, 7…); moods = 221, 222… in that group.
DEFAULT_SFEER_GROUP = 5
DEFAULT_SFEER_ADDRESS = 221  # first scene in a room; 222, 223, …
SFEER_OPTION_OFF = "off"  # select option to clear active mood (HA translation keys must be lowercase)
# Groups 10+ are for software members / other roles — not Sfeer rooms
SFEER_AVOID_GROUPS = frozenset(range(10, 16))


def next_sfeer_group(used_groups: set[int] | list[int] | None = None) -> int:
    """Next free Sfeer room group (start at 5, skip used and reserved groups)."""
    used = set(used_groups or ())
    g = DEFAULT_SFEER_GROUP
    while g in used or g in SFEER_AVOID_GROUPS:
        g += 1
        if g > 15:
            return DEFAULT_SFEER_GROUP
    return g


def sfeer_room_group(entry: dict) -> int:
    """Resolve room-level group from a sfeer config entry."""
    if entry.get("group") is not None:
        return int(entry["group"])
    moods = entry.get("moods") or []
    if moods:
        return int(moods[0].get("group", DEFAULT_SFEER_GROUP))
    return DEFAULT_SFEER_GROUP

# Read-only address — listen-only binary sensor (observe Set/Reset; never control)
DEFAULT_READONLY_GROUP = 1

# BL-AUD audio module — usually group 4
DEFAULT_AUD_GROUP = 4

# RTC (bus clock) — Program write sequence; default group 1 / address 1
DEFAULT_RTC_GROUP = 1
DEFAULT_RTC_ADDRESS = 1
DEFAULT_RTC_SYNC_INTERVAL_HOURS = 12
DEFAULT_RTC_SYNC_MINUTE = 17  # not on the hour
DEFAULT_RTC_SYNC_ON_STARTUP = True
DEFAULT_RTC_SYNC_ON_DST = True
DEFAULT_RTC_DST_DELAY_MINUTES = 1

# Commands (sourced from b_logicx library const)
COMMAND_SET = "Set"
COMMAND_TOGGLE = "Toggle"
COMMAND_DIMMER = "Dimmer"
COMMAND_TIMER = "Timer"
COMMAND_RESET = "Reset"

ON_COMMANDS = [COMMAND_SET, COMMAND_TOGGLE, COMMAND_DIMMER, COMMAND_TIMER]
OFF_COMMANDS = [COMMAND_RESET, COMMAND_TOGGLE, COMMAND_DIMMER]

DEFAULT_ON_COMMAND = COMMAND_SET
DEFAULT_OFF_COMMAND = COMMAND_RESET

# Cover (shutter/roller) datagram pairs are fixed (B-Logicx twin-relay model):
#   open  → Toggle(open)  + Reset(close)
#   close → Toggle(close) + Reset(open)
#   stop  → Toggle(last active direction)
# These are not configurable — hardcoded in cover.py.
#
# After open_time / close_time seconds of commanded motion, Home Assistant
# reports open or closed. Stopping in the middle clears that to unknown.
# The times are not sent on the bus.

DEFAULT_OPEN_TIME = 30.0  # seconds for full open travel
DEFAULT_CLOSE_TIME = 30.0  # seconds for full close travel

# Structure of a monitored address / cover entry in CONF_ADDRESSES:
#
# RLM switch:
# {
#   "name": "Living room light",
#   "type": "rlm",
#   "group": 2,
#   "address": 65,
#   "on_command": "Set",
#   "off_command": "Reset",
#   "check_status": False,
# }
#
# SoftM. Tracking on means Home Assistant is the virtual status module
# (Set/Reset only). Tracking off means a hardware BL-STA already tracks it.
# {
#   "name": "Hall light",
#   "type": "softm",
#   "group": 10,
#   "address": 1,
#   "on_command": "Set",
#   "off_command": "Reset",
#   "enable_softm_status_tracking": True,
#   "check_status": False,
# }
#
# Shutter/cover (ONE entry, TWO bus addresses — open + close only):
# {
#   "name": "Living room blind",
#   "type": "shutter",
#   "open_group": 3,
#   "open_address": 1,
#   "close_group": 3,
#   "close_address": 2,
#   "open_time": 30.0,    # seconds → HA "open" after this (travel estimate)
#   "close_time": 30.0,   # seconds → HA "closed" after this
#   "check_status": False,
# }
#
# Sfeer room (one SelectEntity; moods are virtual addresses, Dimmer activate/off):
# {
#   "name": "Living room",
#   "type": "sfeer",
#   "moods": [
#     {"name": "Dinner", "group": 5, "address": 221},
#     {"name": "TV", "group": 5, "address": 222},
#   ],
#   "check_status": False,
# }
#
# Read-only address (binary_sensor — Status optional, no control commands):
# {
#   "name": "Front door contact",
#   "type": "readonly",
#   "group": 1,
#   "address": 5,
#   "check_status": False,
# }
#
# RTC (bus clock — Program time write; no Status / no control entity):
# {
#   "name": "Bus clock",
#   "type": "rtc",
#   "group": 1,
#   "address": 1,
#   "sync_interval_hours": 12,
#   "sync_minute": 17,
#   "sync_on_startup": True,
#   "sync_on_dst": True,
#   "dst_delay_minutes": 1,
# }
#
# BL-AUD. source_1 … source_8 are the names shown for Misc 0.1 … 0.8.
# LDM and TSM are the same shape as a read-only address: group, address,
# and check_status to ask for a reading when Home Assistant starts.


def is_softm_address(entry: dict) -> bool:
    """True when Home Assistant's Virtual Status Module answers this address.

    Type softm only means the address is a software member. A hardware
    BL-STA may already track it, in which case the per-address flag is off.
    """
    return (
        str(entry.get("type") or "").strip().lower() == ADDRESS_TYPE_SOFTM
        and bool(entry.get("enable_softm_status_tracking"))
    )


def is_switch_address(entry: dict) -> bool:
    """RLM or SoftM switch."""
    t = str(entry.get("type") or "").strip().lower()
    return t in (ADDRESS_TYPE_RLM, ADDRESS_TYPE_SOFTM)


def on_off_from_ha_state(state: str | None) -> bool | None:
    """Map a restored HA state string to on/off, or None if unknown."""
    if state == "on":
        return True
    if state == "off":
        return False
    return None


def get_entity_unique_id(host: str, group: int, address: int) -> str:
    """Generate a stable unique_id for an RLM or SoftM switch entity.

    Uses the gateway host (as entered during initial config) + group + address.
    This makes the unique_id survive:
      - Integration removal + re-add
      - Full CSV re-import (overwrite)
      - HA restarts / reloads

    As long as the same host string and same (group, address) are used,
    Home Assistant will recognize it as the same entity in the entity registry.
    """
    return f"{host}_{group}_{address}"


def get_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    """Generate stable device registry identifiers for one bus address.

    Includes the gateway host so that:
    - Multiple gateways with overlapping bus addresses don't collide.
    - Devices (and their areas, names, etc.) persist across re-creates.
    """
    return {(DOMAIN, f"{host}_{group}_{address}")}


def get_cover_unique_id(
    host: str,
    open_group: int,
    open_address: int,
    close_group: int,
    close_address: int,
) -> str:
    """Stable unique_id for a CoverEntity (open+close address pair)."""
    return f"{host}_cover_{open_group}_{open_address}_{close_group}_{close_address}"


def get_cover_device_identifiers(
    host: str,
    open_group: int,
    open_address: int,
    close_group: int,
    close_address: int,
) -> set[tuple[str, str]]:
    """Stable device registry identifiers for one shutter/cover device."""
    return {
        (
            DOMAIN,
            f"{host}_cover_{open_group}_{open_address}_{close_group}_{close_address}",
        )
    }


def slugify_sfeer_room(name: str) -> str:
    """Stable slug for a Sfeer room name (unique_id / re-import)."""
    import re

    s = (name or "room").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_") or "room"
    return s


def get_sfeer_unique_id(host: str, room_name: str) -> str:
    """Stable unique_id for a Sfeer SelectEntity (one per room)."""
    return f"{host}_sfeer_{slugify_sfeer_room(room_name)}"


def get_sfeer_device_identifiers(host: str, room_name: str) -> set[tuple[str, str]]:
    """Device registry identifiers for one Sfeer room."""
    return {(DOMAIN, get_sfeer_unique_id(host, room_name))}


def get_rtc_unique_id(host: str, group: int, address: int) -> str:
    """Stable unique_id for RTC button / last_sync sensor."""
    return f"{host}_rtc_{group}_{address}"


def get_rtc_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    """Device registry identifiers for one RTC module."""
    return {(DOMAIN, get_rtc_unique_id(host, group, address))}


def get_ldm_unique_id(host: str, group: int, address: int) -> str:
    """Stable unique_id for one light sensor."""
    return f"{host}_ldm_{group}_{address}"


def get_ldm_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    """Device registry id for one light sensor."""
    return {(DOMAIN, get_ldm_unique_id(host, group, address))}


def get_tsm_unique_id(host: str, group: int, address: int) -> str:
    """Stable unique_id for one thermostat."""
    return f"{host}_tsm_{group}_{address}"


def get_tsm_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    """Device registry id for one thermostat."""
    return {(DOMAIN, get_tsm_unique_id(host, group, address))}


def address_device(host: str, addr: dict) -> tuple[set[tuple[str, str]], str, str]:
    """Identifiers, name, and model registered for one stored address."""
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
    elif addr.get("type") == ADDRESS_TYPE_READONLY:
        identifiers = get_device_identifiers(host, addr["group"], addr["address"])
        name = addr.get("name", f"Read-only {addr['group']}.{addr['address']}")
        model = f"Read-only {addr['group']}.{addr['address']}"
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
    elif addr.get("type") == ADDRESS_TYPE_AUD:
        identifiers = get_device_identifiers(
            host, int(addr["group"]), int(addr["address"])
        )
        name = addr.get("name", f"Audio {addr['group']}.{addr['address']}")
        model = f"BL-AUD {addr['group']}.{addr['address']}"
    elif addr.get("type") == ADDRESS_TYPE_TSM:
        identifiers = get_tsm_device_identifiers(
            host, int(addr["group"]), int(addr["address"])
        )
        name = addr.get("name", f"TSM {addr['group']}.{addr['address']}")
        model = f"TSM {addr['group']}.{addr['address']}"
    else:
        # RLM and SoftM switches share one device shape.
        identifiers = get_device_identifiers(host, addr["group"], addr["address"])
        name = addr.get("name", f"{addr['group']}.{addr['address']}")
        model = f"Bus Device {addr['group']}.{addr['address']}"
    return identifiers, name, model


def configured_device_identifiers(
    host: str, addresses: list[dict]
) -> set[tuple[str, str]]:
    """Every device identifier the current address list still owns."""
    keep: set[tuple[str, str]] = set()
    for addr in addresses:
        identifiers, _, _ = address_device(host, addr)
        keep.update(identifiers)
    return keep


def device_no_longer_configured(
    device_identifiers: set[tuple[str, str]],
    keep: set[tuple[str, str]],
) -> bool:
    """True when this device's b_logicx ids are all absent from the address list.

    A device with no b_logicx identifier is left alone.
    """
    ours = {ident for ident in device_identifiers if ident[0] == DOMAIN}
    return bool(ours) and ours.isdisjoint(keep)
