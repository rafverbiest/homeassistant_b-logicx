"""Turn a YAML file into address dicts, and write those dicts back out.

Home Assistant imports are avoided, so the config flow and the offline tests share
one schema. Import replaces the address list only. The SoftM master switch
and the bus repeater stay in Integration settings, and export mentions them
as comments rather than as data the import would apply.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml

try:
    from .const import *
except ImportError:
    from const import *

_LOGGER = logging.getLogger(__name__)

# Keys written after type, name, and the identity fields. A key that an
# address does not have is skipped, so an RLM does not grow player sources.
# Maintaining this order makes YAML files readable
YAML_ORDER = (
    "on_command",
    "off_command",
    "check_status",
    "enable_softm_status_tracking",
    "softm_timer",
    "persist_state",
    "default_state",
    "open_time",
    "close_time",
    "sync_interval_hours",
    "sync_minute",
    "sync_on_startup",
    "sync_on_dst",
    "dst_delay_minutes",
    "source_1",
    "source_2",
    "source_3",
    "source_4",
    "source_5",
    "source_6",
    "source_7",
    "source_8",
    "moods",
)


def entry_sort_key(entry: dict) -> tuple:
    """Sort key for edit/remove pickers: group → address → name."""
    t = entry.get("type")
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


def entry_label(entry: dict) -> str:
    """Picker label: bus address first (matches sort), then name."""
    t = entry.get("type")
    name = entry.get("name") or "Unnamed"
    if t == ADDRESS_TYPE_SHUTTER:
        return (
            f"{entry['open_group']}.{entry['open_address']}/"
            f"{entry['close_group']}.{entry['close_address']} — {name}"
        )
    if t == ADDRESS_TYPE_SFEER:
        return f"{sfeer_room_group(entry)} — {name}"
    return f"{entry.get('group')}.{entry.get('address')} — {name}"


def _yaml_ready_value(value: Any) -> Any:
    """Normalize values for a clean round-trip dump."""
    if isinstance(value, dict):
        return {
            k: _yaml_ready_value(v)
            for k, v in value.items()
            if v is not None
        }
    if isinstance(value, list):
        return [_yaml_ready_value(v) for v in value]
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _ordered_yaml_entry(entry: dict) -> dict:
    """type, name, identity fields, then YAML_ORDER."""
    t = str(entry.get("type") or "")
    if t == ADDRESS_TYPE_SHUTTER:
        identity = ("open_group", "open_address", "close_group", "close_address")
    elif t == ADDRESS_TYPE_SFEER:
        identity = ("group", "moods")
    else:
        identity = ("group", "address")
    order = ("type", "name", *identity, *YAML_ORDER)
    out: dict = {}
    for key in order:
        if key in entry and entry[key] is not None:
            out[key] = entry[key]
    for key in entry:
        if key not in out and entry[key] is not None:
            out[key] = entry[key]
    return out


def _export_entry(entry: dict) -> dict:
    """Copy one address into export order, without unused SoftM keys on an RLM."""
    ready = _yaml_ready_value(dict(entry))
    if ready.get("type") == ADDRESS_TYPE_RLM:
        if not ready.get("enable_softm_status_tracking"):
            ready.pop("enable_softm_status_tracking", None)
        for key in ("persist_state", "default_state", "softm_timer"):
            if not ready.get(key):
                ready.pop(key, None)
    return _ordered_yaml_entry(ready)


def dump_addresses_yaml(
    addresses: list[dict],
    *,
    options: dict[str, Any] | None = None,
) -> str:
    """Serialize addresses to YAML that ``parse_addresses_yaml`` can import.

    Integration options (SoftM master switch, bus repeater) are added as
    comments only — YAML import still replaces the addresses list alone.
    """
    cleaned = [_export_entry(a) for a in addresses]
    # Stable-ish order: same as edit/remove picker
    cleaned = sorted(cleaned, key=entry_sort_key)
    body = yaml.safe_dump(
        {"addresses": cleaned},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    header = (
        "# B-Logicx export — use Import from YAML to load (replaces all addresses)\n"
        "# Types: rlm | softm | aud | shutter | sfeer | readonly | rtc | ldm | tsm\n"
    )
    if options:
        header += (
            "#\n"
            "# Integration settings (not applied by YAML import — use "
            "Integration settings in the UI):\n"
        )
        for key in (
            "softm_tracking_enabled",
            "bus_repeater_enabled",
            "bus_repeater_port",
        ):
            if key not in options:
                continue
            val = options[key]
            if isinstance(val, bool):
                val_s = "true" if val else "false"
            else:
                val_s = str(val)
            header += f"#   {key}: {val_s}\n"
        header += "#\n"
    return header + body


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
    """Validate one address and fill the defaults the rest of the integration expects.

    type is required. An unknown type is rejected. For a softm, an omitted
    enable_softm_status_tracking means on. Tracking on forces Set and Reset,
    forces check_status off, and is the only case where softm_timer is allowed.
    """
    if not isinstance(item, dict):
        raise ValueError("entry must be a mapping")
    raw_type = item.get("type")
    if raw_type is None or str(raw_type).strip() == "":
        raise ValueError("type required")
    t = str(raw_type).strip().lower()
    name = str(item.get("name", "")).strip()
    check = bool(item.get("check_status", False))

    if t in (ADDRESS_TYPE_RLM, ADDRESS_TYPE_SOFTM):
        if not name:
            raise ValueError("name required")
        if t == ADDRESS_TYPE_SOFTM:
            # Omitted flag stays on. False is explicit: a hardware BL-STA
            # already tracks this software member.
            softm_track = bool(item.get("enable_softm_status_tracking", True))
        else:
            if item.get("enable_softm_status_tracking"):
                raise ValueError("type rlm cannot enable SoftM tracking; use type softm")
            softm_track = False
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
        out_type = (
            ADDRESS_TYPE_SOFTM if t == ADDRESS_TYPE_SOFTM else ADDRESS_TYPE_RLM
        )
        if out_type == ADDRESS_TYPE_SOFTM:
            persist = bool(item.get("persist_state", True))
            default_state = bool(item.get("default_state", False))
        else:
            persist = False
            default_state = False
        entry = {
            "name": name,
            "type": out_type,
            "group": int(item["group"]),
            "address": int(item["address"]),
            "on_command": on_cmd,
            "off_command": off_cmd,
            "check_status": False if softm_track else check,
            "enable_softm_status_tracking": softm_track,
            "persist_state": persist,
            "default_state": default_state,
        }
        if softm_timer_val is not None:
            entry["softm_timer"] = softm_timer_val
        return entry

    # Listen-only: Set and Reset update the sensor. Nothing is ever sent.
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

    # check_status here means ask for a reading when Home Assistant starts.
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

    # Same startup reading as an LDM. The request itself is a Status.
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
            # A clock has nothing to answer Status with.
            "check_status": False,
        }

    if t == ADDRESS_TYPE_SHUTTER:
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

    # A blank source name becomes "Source N".
    if t == ADDRESS_TYPE_AUD:
        if not name:
            name = "Audio"
        entry = {
            "name": name,
            "type": ADDRESS_TYPE_AUD,
            "group": int(item.get("group", DEFAULT_AUD_GROUP)),
            "address": int(item["address"]),
        }
        for i in range(1, 9):
            key = f"source_{i}"
            label = str(item.get(key) or "").strip()
            entry[key] = label or f"Source {i}"
        return entry

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
