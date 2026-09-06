"""Pure YAML address config parse (no Home Assistant imports).

Used by config_flow and by CLI tests so the same schema is validated offline.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

try:
    from .const import (
        ADDRESS_TYPE_READONLY,
        ADDRESS_TYPE_LDM,
        ADDRESS_TYPE_NORMAL,
        ADDRESS_TYPE_RTC,
        ADDRESS_TYPE_SFEER,
        ADDRESS_TYPE_SHUTTER,
        ADDRESS_TYPE_TSM,
        DEFAULT_CLOSE_TIME,
        DEFAULT_READONLY_GROUP,
        DEFAULT_LDM_GROUP,
        DEFAULT_TSM_GROUP,
        DEFAULT_OFF_COMMAND,
        DEFAULT_ON_COMMAND,
        DEFAULT_OPEN_TIME,
        DEFAULT_RTC_DST_DELAY_MINUTES,
        DEFAULT_RTC_GROUP,
        DEFAULT_RTC_SYNC_INTERVAL_HOURS,
        DEFAULT_RTC_SYNC_MINUTE,
        DEFAULT_RTC_SYNC_ON_DST,
        DEFAULT_RTC_SYNC_ON_STARTUP,
        DEFAULT_SFEER_GROUP,
        sfeer_room_group,
    )
except ImportError:  # plain `python -m pytest` with ROOT on path
    from const import (
        ADDRESS_TYPE_READONLY,
        ADDRESS_TYPE_LDM,
        ADDRESS_TYPE_NORMAL,
        ADDRESS_TYPE_RTC,
        ADDRESS_TYPE_SFEER,
        ADDRESS_TYPE_SHUTTER,
        ADDRESS_TYPE_TSM,
        DEFAULT_CLOSE_TIME,
        DEFAULT_READONLY_GROUP,
        DEFAULT_LDM_GROUP,
        DEFAULT_TSM_GROUP,
        DEFAULT_OFF_COMMAND,
        DEFAULT_ON_COMMAND,
        DEFAULT_OPEN_TIME,
        DEFAULT_RTC_DST_DELAY_MINUTES,
        DEFAULT_RTC_GROUP,
        DEFAULT_RTC_SYNC_INTERVAL_HOURS,
        DEFAULT_RTC_SYNC_MINUTE,
        DEFAULT_RTC_SYNC_ON_DST,
        DEFAULT_RTC_SYNC_ON_STARTUP,
        DEFAULT_SFEER_GROUP,
        sfeer_room_group,
    )

_LOGGER = logging.getLogger(__name__)


def entry_sort_key(entry: dict) -> tuple:
    """Sort key for edit/remove pickers: group → address → name."""
    t = entry.get("type", ADDRESS_TYPE_NORMAL)
    name = str(entry.get("name") or "")
    if t == ADDRESS_TYPE_SHUTTER:
        return (
            int(entry.get("open_group", 0)),
            int(entry.get("open_address", 0)),
            name,
        )
    if t == ADDRESS_TYPE_SFEER:
        return (int(sfeer_room_group(entry)), 0, name)
    return (
        int(entry.get("group", 0)),
        int(entry.get("address", 0)),
        name,
    )


def entries_sorted_for_picker(addresses: list[dict]) -> list[dict]:
    """Return addresses sorted group → address for edit/remove dropdowns."""
    return sorted(addresses, key=entry_sort_key)


def parse_addresses_yaml(content: str) -> tuple[list[dict], str | None]:
    """Parse YAML into address list. Returns (entries, error_key)."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as err:
        _LOGGER.error("YAML parse error: %s", err)
        return [], "invalid_yaml"

    if not isinstance(data, dict):
        _LOGGER.error("YAML root must be a mapping with 'addresses' list")
        return [], "invalid_format"

    raw_list = data.get("addresses")
    if raw_list is None:
        _LOGGER.error("YAML missing 'addresses' key")
        return [], "invalid_format"
    if not isinstance(raw_list, list):
        _LOGGER.error("'addresses' must be a list")
        return [], "invalid_format"

    result: list[dict] = []
    for i, item in enumerate(raw_list):
        try:
            parsed = normalize_yaml_entry(item)
            result.append(parsed)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("YAML addresses[%s]: %s — %s", i, err, item)
            return [], "invalid_format"

    _LOGGER.info("YAML import parsed %d entries", len(result))
    if not result:
        return [], "invalid_format"
    return result, None


def normalize_yaml_entry(item: Any) -> dict:
    """Validate and normalise one YAML address dict."""
    if not isinstance(item, dict):
        raise ValueError("entry must be a mapping")
    t = str(item.get("type", ADDRESS_TYPE_NORMAL)).strip().lower()
    name = str(item.get("name", "")).strip()
    check = bool(item.get("check_status", False))

    if t == ADDRESS_TYPE_NORMAL:
        if not name:
            raise ValueError("name required")
        softm_track = bool(item.get("enable_softm_status_tracking", False))
        if softm_track and check:
            raise ValueError(
                "check_status and enable_softm_status_tracking cannot both be true"
            )
        on_cmd = str(item.get("on_command") or DEFAULT_ON_COMMAND).strip()
        off_cmd = str(item.get("off_command") or DEFAULT_OFF_COMMAND).strip()
        if softm_track and (
            on_cmd != DEFAULT_ON_COMMAND or off_cmd != DEFAULT_OFF_COMMAND
        ):
            # SoftM VSM answers Toggle; HA must use absolute Set/Reset only
            raise ValueError(
                "enable_softm_status_tracking requires on_command: Set and "
                "off_command: Reset (Toggle would double-flip)"
            )
        softm_timer = item.get("softm_timer")
        if softm_timer is not None and softm_timer != "":
            if not softm_track:
                raise ValueError(
                    "softm_timer requires enable_softm_status_tracking"
                )
            softm_timer_val: float | None = float(softm_timer)
            if softm_timer_val <= 0:
                raise ValueError("softm_timer must be > 0")
        else:
            softm_timer_val = None
        persist = bool(item.get("persist_state", True if softm_track else False))
        default_state = bool(item.get("default_state", False))
        entry = {
            "name": name,
            "type": ADDRESS_TYPE_NORMAL,
            "group": int(item["group"]),
            "address": int(item["address"]),
            "on_command": on_cmd,
            "off_command": off_cmd,
            "check_status": False if softm_track else check,
            "enable_softm_status_tracking": softm_track,
            "persist_state": persist if softm_track else False,
            "default_state": default_state if softm_track else False,
        }
        if softm_timer_val is not None:
            entry["softm_timer"] = softm_timer_val
        return entry

    if t == ADDRESS_TYPE_READONLY:
        if not name:
            raise ValueError("name required")
        return {
            "name": name,
            "type": ADDRESS_TYPE_READONLY,
            "group": int(item.get("group", DEFAULT_READONLY_GROUP)),
            "address": int(item["address"]),
            "check_status": check,
        }

    if t == ADDRESS_TYPE_LDM:
        if not name:
            name = "Light sensor"
        return {
            "name": name,
            "type": ADDRESS_TYPE_LDM,
            "group": int(item.get("group", DEFAULT_LDM_GROUP)),
            "address": int(item["address"]),
            "check_status": check,
        }

    if t == ADDRESS_TYPE_TSM:
        if not name:
            name = "Temperature"
        return {
            "name": name,
            "type": ADDRESS_TYPE_TSM,
            "group": int(item.get("group", DEFAULT_TSM_GROUP)),
            "address": int(item["address"]),
            "check_status": check,
        }

    if t == ADDRESS_TYPE_RTC:
        if not name:
            name = "Bus clock"
        return {
            "name": name,
            "type": ADDRESS_TYPE_RTC,
            "group": int(item.get("group", DEFAULT_RTC_GROUP)),
            "address": int(item["address"]),
            "sync_interval_hours": float(
                item.get(
                    "sync_interval_hours", DEFAULT_RTC_SYNC_INTERVAL_HOURS
                )
                or DEFAULT_RTC_SYNC_INTERVAL_HOURS
            ),
            "sync_minute": int(
                item.get("sync_minute", DEFAULT_RTC_SYNC_MINUTE)
                if item.get("sync_minute", DEFAULT_RTC_SYNC_MINUTE) is not None
                else DEFAULT_RTC_SYNC_MINUTE
            ),
            "sync_on_startup": bool(
                item.get("sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP)
            ),
            "sync_on_dst": bool(
                item.get("sync_on_dst", DEFAULT_RTC_SYNC_ON_DST)
            ),
            "dst_delay_minutes": int(
                item.get("dst_delay_minutes", DEFAULT_RTC_DST_DELAY_MINUTES)
                if item.get("dst_delay_minutes", DEFAULT_RTC_DST_DELAY_MINUTES)
                is not None
                else DEFAULT_RTC_DST_DELAY_MINUTES
            ),
            "check_status": False,
        }

    if t in (ADDRESS_TYPE_SHUTTER, "cover", "roller", "blind"):
        if not name:
            name = "Cover"
        return {
            "name": name,
            "type": ADDRESS_TYPE_SHUTTER,
            "open_group": int(item["open_group"]),
            "open_address": int(item["open_address"]),
            "close_group": int(item["close_group"]),
            "close_address": int(item["close_address"]),
            "open_time": float(
                item.get("open_time", DEFAULT_OPEN_TIME) or DEFAULT_OPEN_TIME
            ),
            "close_time": float(
                item.get("close_time", DEFAULT_CLOSE_TIME) or DEFAULT_CLOSE_TIME
            ),
            "check_status": check,
        }

    if t == ADDRESS_TYPE_SFEER:
        if not name:
            raise ValueError("sfeer room name required")
        moods_in = item.get("moods") or []
        if not isinstance(moods_in, list):
            raise ValueError("moods must be a list")
        # Room group: explicit, else legacy from first mood, else default 5
        if item.get("group") is not None:
            room_group = int(item["group"])
        elif moods_in and isinstance(moods_in[0], dict) and "group" in moods_in[0]:
            room_group = int(moods_in[0]["group"])
        else:
            room_group = DEFAULT_SFEER_GROUP

        moods = []
        for m in moods_in:
            if not isinstance(m, dict):
                raise ValueError("mood must be a mapping")
            mn = str(m.get("name", "")).strip()
            if not mn:
                raise ValueError("mood name required")
            # Moods inherit room group (YAML may omit group on each mood)
            moods.append(
                {
                    "name": mn,
                    "group": room_group,
                    "address": int(m["address"]),
                }
            )
        return {
            "name": name,
            "type": ADDRESS_TYPE_SFEER,
            "group": room_group,
            "moods": moods,
            "check_status": check,
        }

    raise ValueError(f"unknown type {t!r}")
