"""Constants for the B-Logicx Home Assistant integration."""

DOMAIN = "b_logicx"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_ADDRESSES = "addresses"

# Entry options (integration-level)
CONF_SOFTM_TRACKING_ENABLED = "softm_tracking_enabled"
CONF_BUS_REPEATER_ENABLED = "bus_repeater_enabled"
CONF_BUS_REPEATER_PORT = "bus_repeater_port"
DEFAULT_BUS_REPEATER_PORT = 10001

# The default port is defined in the library (single source of truth)
try:
    from .b_logicx.const import BLX_TCP_PORT as DEFAULT_PORT
except ImportError:  # offline tests with flat sys.path
    from b_logicx.const import BLX_TCP_PORT as DEFAULT_PORT

# Address / entity types
ADDRESS_TYPE_NORMAL = "normal"
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
SFEER_OPTION_OFF = "Off"  # select option to clear active mood
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
# Travel times (v0.5.1): after open_time / close_time seconds of commanded
# motion, HA reports open / closed. Mid-stop clears to unknown. Bus traffic
# is unchanged — times only affect Home Assistant state.

DEFAULT_OPEN_TIME = 30.0  # seconds for full open travel
DEFAULT_CLOSE_TIME = 30.0  # seconds for full close travel

# Structure of a monitored address / cover entry in CONF_ADDRESSES:
#
# Normal switch:
# {
#   "name": "Living room light",
#   "type": "normal",
#   "group": 2,
#   "address": 65,
#   "on_command": "Set",
#   "off_command": "Reset",
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


def get_entity_unique_id(host: str, group: int, address: int) -> str:
    """Generate a stable unique_id for a normal bus-address switch entity.

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
    """Generate stable device registry identifiers for a normal bus address.

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
    return f"{host}_ldm_{group}_{address}"


def get_ldm_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    return {(DOMAIN, get_ldm_unique_id(host, group, address))}


def get_tsm_unique_id(host: str, group: int, address: int) -> str:
    return f"{host}_tsm_{group}_{address}"


def get_tsm_device_identifiers(host: str, group: int, address: int) -> set[tuple[str, str]]:
    return {(DOMAIN, get_tsm_unique_id(host, group, address))}
