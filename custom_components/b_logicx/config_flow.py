"""Config flow and options flow for B-Logicx integration."""

from __future__ import annotations

import base64
import logging
from typing import Any

from homeassistant.components.file_upload import process_uploaded_file

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

import ipaddress

from .address_config import entries_sorted_for_picker, parse_addresses_yaml
from .const import (
    ADDRESS_TYPE_READONLY,
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_NORMAL,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_BUS_REPEATER_ENABLED,
    CONF_BUS_REPEATER_PORT,
    CONF_PORT,
    CONF_SOFTM_TRACKING_ENABLED,
    DEFAULT_BUS_REPEATER_PORT,
    DEFAULT_CLOSE_TIME,
    DEFAULT_READONLY_GROUP,
    DEFAULT_LDM_GROUP,
    DEFAULT_OFF_COMMAND,
    DEFAULT_ON_COMMAND,
    DEFAULT_OPEN_TIME,
    DEFAULT_PORT,
    DEFAULT_RTC_DST_DELAY_MINUTES,
    DEFAULT_RTC_GROUP,
    DEFAULT_RTC_SYNC_INTERVAL_HOURS,
    DEFAULT_RTC_SYNC_MINUTE,
    DEFAULT_RTC_SYNC_ON_DST,
    DEFAULT_RTC_SYNC_ON_STARTUP,
    DEFAULT_SFEER_ADDRESS,
    DEFAULT_SFEER_GROUP,
    DEFAULT_TSM_GROUP,
    DOMAIN,
    OFF_COMMANDS,
    ON_COMMANDS,
    next_sfeer_group,
    sfeer_room_group,
)

_LOGGER = logging.getLogger(__name__)


def _command_selector(options: list[str], default: str) -> Any:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=c, label=c) for c in options],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _entry_key(entry: dict) -> str:
    """Stable key for edit/remove menus."""
    t = entry.get("type", ADDRESS_TYPE_NORMAL)
    if t == ADDRESS_TYPE_SHUTTER:
        return (
            f"cover:{entry['open_group']}.{entry['open_address']}"
            f":{entry['close_group']}.{entry['close_address']}"
        )
    if t == ADDRESS_TYPE_SFEER:
        return f"sfeer:{entry.get('name', '')}"
    return f"addr:{entry['group']}.{entry['address']}"


def _entry_label(entry: dict) -> str:
    t = entry.get("type", ADDRESS_TYPE_NORMAL)
    if t == ADDRESS_TYPE_SHUTTER:
        return (
            f"{entry.get('name', 'Cover')} "
            f"(open {entry['open_group']}.{entry['open_address']} / "
            f"close {entry['close_group']}.{entry['close_address']})"
        )
    if t == ADDRESS_TYPE_SFEER:
        g = sfeer_room_group(entry)
        moods = entry.get("moods") or []
        mood_bits = ", ".join(
            f"{m.get('name')} {g}.{m.get('address')}" for m in moods
        )
        return (
            f"Sfeer: {entry.get('name', 'Room')} (group {g}) "
            f"[{mood_bits or 'no moods yet'}]"
        )
    if t == ADDRESS_TYPE_READONLY:
        return (
            f"Read-only {entry.get('group')}.{entry.get('address')} - "
            f"{entry.get('name', 'Unnamed')}"
        )
    if t == ADDRESS_TYPE_RTC:
        return (
            f"RTC {entry.get('group')}.{entry.get('address')} — "
            f"{entry.get('name', 'Bus clock')} "
            f"(every {entry.get('sync_interval_hours', 12)}h @ :{int(entry.get('sync_minute', 17)):02d})"
        )
    if t == ADDRESS_TYPE_LDM:
        return (
            f"LDM {entry.get('group')}.{entry.get('address')} — "
            f"{entry.get('name', 'Light sensor')}"
        )
    if t == ADDRESS_TYPE_TSM:
        return (
            f"TSM {entry.get('group')}.{entry.get('address')} — "
            f"{entry.get('name', 'Temperature')}"
        )
    return (
        f"{entry.get('group')}.{entry.get('address')} - "
        f"{entry.get('name', 'Unnamed')}"
    )


def _find_entry(addresses: list[dict], key: str) -> dict | None:
    for entry in addresses:
        if _entry_key(entry) == key:
            return entry
    return None


def _upsert_by_key(addresses: list[dict], new_entry: dict) -> list[dict]:
    """Replace entry with same _entry_key, else append."""
    key = _entry_key(new_entry)
    for i, addr in enumerate(addresses):
        if _entry_key(addr) == key:
            addresses[i] = new_entry
            return addresses
    # Normal/read-only: also match by group+address across type changes
    t = new_entry.get("type")
    if t in (ADDRESS_TYPE_NORMAL, ADDRESS_TYPE_READONLY):
        for i, addr in enumerate(addresses):
            if addr.get("type") in (ADDRESS_TYPE_NORMAL, ADDRESS_TYPE_READONLY, None):
                if (
                    addr.get("group") == new_entry["group"]
                    and addr.get("address") == new_entry["address"]
                ):
                    addresses[i] = new_entry
                    return addresses
    if t == ADDRESS_TYPE_SHUTTER:
        for i, addr in enumerate(addresses):
            if (
                addr.get("type") == ADDRESS_TYPE_SHUTTER
                and addr.get("open_group") == new_entry["open_group"]
                and addr.get("open_address") == new_entry["open_address"]
                and addr.get("close_group") == new_entry["close_group"]
                and addr.get("close_address") == new_entry["close_address"]
            ):
                addresses[i] = new_entry
                return addresses
    if t == ADDRESS_TYPE_SFEER:
        for i, addr in enumerate(addresses):
            if (
                addr.get("type") == ADDRESS_TYPE_SFEER
                and addr.get("name") == new_entry["name"]
            ):
                addresses[i] = new_entry
                return addresses
    addresses.append(new_entry)
    return addresses


def _picker_options(addresses: list[dict]) -> list[selector.SelectOptionDict]:
    """Dropdown options for edit/remove, sorted group → address."""
    return [
        selector.SelectOptionDict(value=_entry_key(a), label=_entry_label(a))
        for a in entries_sorted_for_picker(addresses)
    ]


def _read_uploaded_text(hass, file_id: str) -> str:
    """Read uploaded file (blocking — run in executor)."""
    with process_uploaded_file(hass, file_id) as file_path:
        raw = file_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _yaml_template() -> str:
    """Prefer on-disk template.yaml so HA download matches the repo file."""
    from pathlib import Path

    path = Path(__file__).resolve().parent / "template.yaml"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return """# B-Logicx addresses (full replace on import)
# Types: normal | shutter | sfeer | readonly | rtc

addresses:
  - type: normal
    name: Kitchen Light
    group: 2
    address: 33
    on_command: Set
    off_command: Reset
    check_status: true

  - type: shutter
    name: Office Blind
    open_group: 3
    open_address: 20
    close_group: 3
    close_address: 21
    open_time: 30
    close_time: 30
    check_status: true

  - type: sfeer
    name: Lounge
    check_status: true
    moods:
      - name: Reading
        group: 5
        address: 221
      - name: Cinema
        group: 5
        address: 222

  - type: readonly
    name: Example read-only input
    group: 1
    address: 30
    check_status: false

  - type: rtc
    name: Bus clock
    group: 1
    address: 1
    sync_interval_hours: 12
    sync_minute: 17
    sync_on_startup: true
    sync_on_dst: true
    dst_delay_minutes: 1

  - type: normal
    name: Software Member Example
    group: 10
    address: 200
    on_command: Toggle
    off_command: Reset
    check_status: false
"""


class BLogicxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for B-Logicx (gateway IP)."""

    VERSION = 4

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for the BL-NWM IP address (gateway)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                try:
                    ipaddress.ip_address(host)
                    validated_host = host
                except ValueError:
                    if (
                        not host
                        or ".." in host
                        or host.startswith(".")
                        or host.endswith(".")
                        or len(host) > 253
                    ):
                        raise vol.Invalid("invalid_host")
                    for label in host.split("."):
                        if not label or len(label) > 63:
                            raise vol.Invalid("invalid_host")
                    validated_host = host
            except Exception:
                errors[CONF_HOST] = "invalid_host"
            else:
                await self.async_set_unique_id(validated_host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"B-Logicx {validated_host}",
                    data={
                        CONF_HOST: validated_host,
                        CONF_PORT: port,
                        CONF_ADDRESSES: [],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowWithConfigEntry:
        return BLogicxOptionsFlow(config_entry)


class BLogicxOptionsFlow(OptionsFlowWithConfigEntry):
    """Options: add/edit/remove entries; YAML import/template."""

    def _finish_options(self) -> FlowResult:
        """End the options flow without wiping SoftM / repeater settings.

        ``async_create_entry(data=...)`` replaces ``config_entry.options``.
        Address add/edit/remove must preserve the current options dict.
        """
        return self.async_create_entry(
            title="", data=dict(self.config_entry.options)
        )

    async def _save_and_reload(self, addresses: list[dict]) -> None:
        """Persist addresses. Reload is handled by the entry update listener."""
        new_data = {**self.config_entry.data, CONF_ADDRESSES: addresses}
        self.hass.config_entries.async_update_entry(
            self.config_entry, data=new_data
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        # List form → labels come from translations (options.step.init.menu_options.*)
        menu_options: list[str] = [
            "add_address",
            "add_sfeer_room",
        ]
        if any(a.get("type") == ADDRESS_TYPE_SFEER for a in current):
            menu_options.append("add_sfeer_mood")
        if current:
            menu_options.extend(["edit_select", "remove_select"])
        menu_options.extend(
            [
                "integration_settings",
                "download_yaml_template",
                "import_yaml",
            ]
        )

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={
                "entry_count": str(len(current)),
            },
        )

    async def async_step_integration_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """SoftM tracking master switch + TCP bus repeater."""
        if user_input is not None:
            opts = {
                **self.config_entry.options,
                CONF_SOFTM_TRACKING_ENABLED: user_input.get(
                    CONF_SOFTM_TRACKING_ENABLED, False
                ),
                CONF_BUS_REPEATER_ENABLED: user_input.get(
                    CONF_BUS_REPEATER_ENABLED, False
                ),
                CONF_BUS_REPEATER_PORT: int(
                    user_input.get(
                        CONF_BUS_REPEATER_PORT, DEFAULT_BUS_REPEATER_PORT
                    )
                ),
            }
            return self.async_create_entry(title="", data=opts)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="integration_settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SOFTM_TRACKING_ENABLED,
                        default=opts.get(CONF_SOFTM_TRACKING_ENABLED, False),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_BUS_REPEATER_ENABLED,
                        default=opts.get(CONF_BUS_REPEATER_ENABLED, False),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_BUS_REPEATER_PORT,
                        default=int(
                            opts.get(
                                CONF_BUS_REPEATER_PORT, DEFAULT_BUS_REPEATER_PORT
                            )
                        ),
                    ): int,
                }
            )
        )

    async def async_step_add_address(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            t = user_input.get("address_type", ADDRESS_TYPE_NORMAL)
            if t == ADDRESS_TYPE_SHUTTER:
                return await self.async_step_add_shutter()
            if t == ADDRESS_TYPE_READONLY:
                return await self.async_step_add_readonly()
            if t == ADDRESS_TYPE_RTC:
                return await self.async_step_add_rtc()
            if t == ADDRESS_TYPE_LDM:
                return await self.async_step_add_ldm()
            if t == ADDRESS_TYPE_TSM:
                return await self.async_step_add_tsm()
            return await self.async_step_add_normal()

        return self.async_show_form(
            step_id="add_address",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address_type", default=ADDRESS_TYPE_NORMAL
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                ADDRESS_TYPE_NORMAL,
                                ADDRESS_TYPE_READONLY,
                                ADDRESS_TYPE_SHUTTER,
                                ADDRESS_TYPE_RTC,
                                ADDRESS_TYPE_LDM,
                                ADDRESS_TYPE_TSM,
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="address_type",
                        )
                    ),
                }
            ),
        )

    async def async_step_add_normal(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            softm = bool(user_input.get("enable_softm_status_tracking", False))
            check = bool(user_input.get("check_status", False))
            on_cmd = user_input.get("on_command", DEFAULT_ON_COMMAND)
            off_cmd = user_input.get("off_command", DEFAULT_OFF_COMMAND)
            if softm and check:
                errors["base"] = "softm_check_conflict"
            elif softm and (
                on_cmd != DEFAULT_ON_COMMAND or off_cmd != DEFAULT_OFF_COMMAND
            ):
                errors["base"] = "softm_command_conflict"
            else:
                new_addr: dict[str, Any] = {
                    "name": user_input["name"].strip(),
                    "type": ADDRESS_TYPE_NORMAL,
                    "group": int(user_input["group"]),
                    "address": int(user_input["address"]),
                    "on_command": on_cmd,
                    "off_command": off_cmd,
                    "check_status": False if softm else check,
                    "enable_softm_status_tracking": softm,
                    "persist_state": bool(
                        user_input.get("persist_state", True)
                    )
                    if softm
                    else False,
                    "default_state": bool(
                        user_input.get("default_state", False)
                    )
                    if softm
                    else False,
                }
                timer = user_input.get("softm_timer")
                if softm and timer not in (None, ""):
                    timer_val = float(timer)
                    if timer_val > 0:
                        new_addr["softm_timer"] = timer_val
                addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
                edit_key = getattr(self, "_edit_key", None)
                if edit_key:
                    addresses = [
                        a for a in addresses if _entry_key(a) != edit_key
                    ]
                    self._edit_key = None
                addresses = _upsert_by_key(addresses, new_addr)
                await self._save_and_reload(addresses)
                return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        softm_def = bool(defaults.get("enable_softm_status_tracking", False))
        return self.async_show_form(
            step_id="add_normal",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "group", default=defaults.get("group", 2)
                    ): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Required(
                        "on_command",
                        default=defaults.get("on_command", DEFAULT_ON_COMMAND),
                    ): _command_selector(ON_COMMANDS, DEFAULT_ON_COMMAND),
                    vol.Required(
                        "off_command",
                        default=defaults.get(
                            "off_command", DEFAULT_OFF_COMMAND
                        ),
                    ): _command_selector(OFF_COMMANDS, DEFAULT_OFF_COMMAND),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False)
                        if not softm_def
                        else False,
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "enable_softm_status_tracking",
                        default=softm_def,
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "softm_timer",
                        default=defaults.get("softm_timer", 0) or 0,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=86400,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "persist_state",
                        default=defaults.get("persist_state", True),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "default_state",
                        default=defaults.get("default_state", False),
                    ): selector.BooleanSelector(),
                }
            ),
            errors=errors
        )

    async def async_step_add_readonly(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add read-only (listen-only) binary sensor."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_READONLY,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "check_status": user_input.get("check_status", False),
            }
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                addresses = [a for a in addresses if _entry_key(a) != edit_key]
                self._edit_key = None
            addresses = _upsert_by_key(addresses, new_addr)
            await self._save_and_reload(addresses)
            return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return self.async_show_form(
            step_id="add_readonly",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_READONLY_GROUP)),
                    ): int,
                    vol.Required(
                        "address", default=int(defaults.get("address", 0))
                    ): int,
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            )
        )

    async def async_step_add_ldm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add LDM light sensor (Value+System; request via Data 0.2 + Select)."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Light sensor",
                "type": ADDRESS_TYPE_LDM,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "check_status": user_input.get("check_status", False),
            }
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                addresses = [a for a in addresses if _entry_key(a) != edit_key]
                self._edit_key = None
            addresses = _upsert_by_key(addresses, new_addr)
            await self._save_and_reload(addresses)
            return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return self.async_show_form(
            step_id="add_ldm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Light sensor")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_LDM_GROUP)),
                    ): int,
                    vol.Required(
                        "address", default=int(defaults.get("address", 0))
                    ): int,
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            )
        )

    async def async_step_add_tsm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add TSM temperature / thermostat telemetry."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Temperature",
                "type": ADDRESS_TYPE_TSM,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "check_status": user_input.get("check_status", False),
            }
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                addresses = [a for a in addresses if _entry_key(a) != edit_key]
                self._edit_key = None
            addresses = _upsert_by_key(addresses, new_addr)
            await self._save_and_reload(addresses)
            return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return self.async_show_form(
            step_id="add_tsm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Temperature")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_TSM_GROUP)),
                    ): int,
                    vol.Required(
                        "address", default=int(defaults.get("address", 0))
                    ): int,
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            )
        )

    async def async_step_add_rtc(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add bus RTC (clock) for periodic Program time sync."""
        if user_input is not None:
            new_addr = {
                "name": user_input["name"].strip() or "Bus clock",
                "type": ADDRESS_TYPE_RTC,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "sync_interval_hours": float(
                    user_input.get(
                        "sync_interval_hours", DEFAULT_RTC_SYNC_INTERVAL_HOURS
                    )
                ),
                "sync_minute": int(
                    user_input.get("sync_minute", DEFAULT_RTC_SYNC_MINUTE)
                ),
                "sync_on_startup": user_input.get(
                    "sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP
                ),
                "sync_on_dst": user_input.get(
                    "sync_on_dst", DEFAULT_RTC_SYNC_ON_DST
                ),
                "dst_delay_minutes": int(
                    user_input.get(
                        "dst_delay_minutes", DEFAULT_RTC_DST_DELAY_MINUTES
                    )
                ),
                "check_status": False,
            }
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                addresses = [a for a in addresses if _entry_key(a) != edit_key]
                self._edit_key = None
            addresses = _upsert_by_key(addresses, new_addr)
            await self._save_and_reload(addresses)
            return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return self.async_show_form(
            step_id="add_rtc",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "name", default=defaults.get("name", "Bus clock")
                    ): str,
                    vol.Required(
                        "group",
                        default=int(defaults.get("group", DEFAULT_RTC_GROUP)),
                    ): int,
                    vol.Required(
                        "address",
                        default=int(defaults.get("address", 1)),
                    ): int,
                    vol.Required(
                        "sync_interval_hours",
                        default=float(
                            defaults.get(
                                "sync_interval_hours",
                                DEFAULT_RTC_SYNC_INTERVAL_HOURS,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=168,
                            step=1,
                            unit_of_measurement="h",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        "sync_minute",
                        default=int(
                            defaults.get(
                                "sync_minute", DEFAULT_RTC_SYNC_MINUTE
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=59,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "sync_on_startup",
                        default=bool(
                            defaults.get(
                                "sync_on_startup", DEFAULT_RTC_SYNC_ON_STARTUP
                            )
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        "sync_on_dst",
                        default=bool(
                            defaults.get("sync_on_dst", DEFAULT_RTC_SYNC_ON_DST)
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        "dst_delay_minutes",
                        default=int(
                            defaults.get(
                                "dst_delay_minutes",
                                DEFAULT_RTC_DST_DELAY_MINUTES,
                            )
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=60,
                            step=1,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        )

    async def async_step_add_shutter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            new_cover = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_SHUTTER,
                "open_group": int(user_input["open_group"]),
                "open_address": int(user_input["open_address"]),
                "close_group": int(user_input["close_group"]),
                "close_address": int(user_input["close_address"]),
                "open_time": float(
                    user_input.get("open_time", DEFAULT_OPEN_TIME)
                ),
                "close_time": float(
                    user_input.get("close_time", DEFAULT_CLOSE_TIME)
                ),
                "check_status": user_input.get("check_status", False),
            }
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                addresses = [a for a in addresses if _entry_key(a) != edit_key]
                self._edit_key = None
            addresses = _upsert_by_key(addresses, new_cover)
            await self._save_and_reload(addresses)
            return self._finish_options()

        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return self.async_show_form(
            step_id="add_shutter",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "open_group", default=defaults.get("open_group", 3)
                    ): int,
                    vol.Required(
                        "open_address",
                        default=defaults.get("open_address", 0),
                    ): int,
                    vol.Required(
                        "close_group", default=defaults.get("close_group", 3)
                    ): int,
                    vol.Required(
                        "close_address",
                        default=defaults.get("close_address", 0),
                    ): int,
                    vol.Required(
                        "open_time",
                        default=float(
                            defaults.get("open_time", DEFAULT_OPEN_TIME)
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=600,
                            step=0.5,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        "close_time",
                        default=float(
                            defaults.get("close_time", DEFAULT_CLOSE_TIME)
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=600,
                            step=0.5,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_add_sfeer_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create or edit a Sfeer room (one bus group; moods added separately)."""
        current = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        defaults = getattr(self, "_edit_defaults", {}) or {}
        editing = bool(getattr(self, "_edit_key", None))

        if user_input is not None:
            room_name = user_input["room_name"].strip()
            room_group = int(user_input["group"])
            check = user_input.get("check_status", False)
            edit_key = getattr(self, "_edit_key", None)
            if edit_key:
                old = _find_entry(current, edit_key) or {}
                moods = list(old.get("moods") or [])
                # Keep moods, rewrite their group if room group changed
                moods = [
                    {
                        "name": m["name"],
                        "group": room_group,
                        "address": int(m["address"]),
                    }
                    for m in moods
                ]
                self._edit_key = None
                self._edit_defaults = None
                current = [a for a in current if _entry_key(a) != edit_key]
            else:
                moods = []
            new_room = {
                "name": room_name,
                "type": ADDRESS_TYPE_SFEER,
                "group": room_group,
                "moods": moods,
                "check_status": check,
            }
            current = _upsert_by_key(current, new_room)
            await self._save_and_reload(current)
            return self._finish_options()

        used = {
            sfeer_room_group(a)
            for a in current
            if a.get("type") == ADDRESS_TYPE_SFEER
            and (
                not editing
                or _entry_key(a) != getattr(self, "_edit_key", None)
            )
        }
        if editing and defaults:
            def_group = sfeer_room_group(defaults)
            def_name = defaults.get("name", "")
            def_check = defaults.get("check_status", False)
            moods = defaults.get("moods") or []
            mood_desc = (
                ", ".join(f"{m.get('name')} → {m.get('address')}" for m in moods)
                or "(none yet — use Add Sfeer)"
            )
        else:
            def_group = next_sfeer_group(used)
            def_name = ""
            def_check = False
            mood_desc = "(none yet — use Add Sfeer after creating the room)"
            self._edit_defaults = None

        return self.async_show_form(
            step_id="add_sfeer_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room_name", default=def_name): str,
                    vol.Required("group", default=def_group): int,
                    vol.Optional(
                        "check_status", default=def_check
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders={"moods": mood_desc},
        )

    async def async_step_add_sfeer_mood(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: pick Sfeer room (group is shown in the label)."""
        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        rooms = [a for a in current if a.get("type") == ADDRESS_TYPE_SFEER]
        if not rooms:
            return await self.async_step_init()

        if user_input is not None:
            self._sfeer_mood_room_key = user_input["room"]
            return await self.async_step_add_sfeer_mood_details()

        room_options = [
            selector.SelectOptionDict(
                value=_entry_key(r),
                label=(
                    f"{r.get('name', 'Room')} "
                    f"(group {sfeer_room_group(r)})"
                ),
            )
            for r in entries_sorted_for_picker(rooms)
        ]
        return self.async_show_form(
            step_id="add_sfeer_mood",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=room_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            )
        )

    async def async_step_add_sfeer_mood_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: mood name + address; group fixed to the room's group."""
        current = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        room_key = getattr(self, "_sfeer_mood_room_key", None)
        room = _find_entry(current, room_key) if room_key else None
        if not room or room.get("type") != ADDRESS_TYPE_SFEER:
            return await self.async_step_add_sfeer_mood()

        room_group = sfeer_room_group(room)
        moods = list(room.get("moods") or [])
        if moods:
            def_addr = max(int(m.get("address", 0)) for m in moods) + 1
        else:
            def_addr = DEFAULT_SFEER_ADDRESS

        if user_input is not None:
            moods.append(
                {
                    "name": user_input["mood_name"].strip(),
                    "group": room_group,
                    "address": int(user_input["address"]),
                }
            )
            new_room = {
                "name": room["name"],
                "type": ADDRESS_TYPE_SFEER,
                "group": room_group,
                "moods": moods,
                "check_status": room.get("check_status", False),
            }
            addresses = [a for a in current if _entry_key(a) != room_key]
            addresses = _upsert_by_key(addresses, new_room)
            self._sfeer_mood_room_key = None
            await self._save_and_reload(addresses)
            return self._finish_options()

        return self.async_show_form(
            step_id="add_sfeer_mood_details",
            data_schema=vol.Schema(
                {
                    vol.Required("mood_name"): str,
                    vol.Required("address", default=def_addr): int,
                }
            ),
            description_placeholders={
                "room_name": str(room.get("name", "")),
                "group": str(room_group),
            },
        )

    async def async_step_edit_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._edit_key = user_input["entry_to_edit"]
            current = self.config_entry.data.get(CONF_ADDRESSES, [])
            entry = _find_entry(current, self._edit_key) or {}
            self._edit_defaults = dict(entry)
            t = entry.get("type")
            if t == ADDRESS_TYPE_SHUTTER:
                return await self.async_step_add_shutter()
            if t == ADDRESS_TYPE_SFEER:
                return await self.async_step_add_sfeer_room()
            if t == ADDRESS_TYPE_READONLY:
                return await self.async_step_add_readonly()
            if t == ADDRESS_TYPE_RTC:
                return await self.async_step_add_rtc()
            if t == ADDRESS_TYPE_LDM:
                return await self.async_step_add_ldm()
            if t == ADDRESS_TYPE_TSM:
                return await self.async_step_add_tsm()
            return await self.async_step_add_normal()

        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        return self.async_show_form(
            step_id="edit_select",
            data_schema=vol.Schema(
                {
                    vol.Required("entry_to_edit"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_picker_options(current),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_remove_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._remove_key = user_input["entry_to_remove"]
            return await self.async_step_remove_confirm()

        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        return self.async_show_form(
            step_id="remove_select",
            data_schema=vol.Schema(
                {
                    vol.Required("entry_to_remove"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_picker_options(current),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_remove_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        key = getattr(self, "_remove_key", None)
        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        entry = _find_entry(current, key) if key else None
        label = _entry_label(entry) if entry else (key or "unknown")

        if user_input is not None:
            if user_input.get("confirm"):
                addresses = [a for a in current if _entry_key(a) != key]
                await self._save_and_reload(addresses)
            self._remove_key = None
            return self._finish_options()

        return self.async_show_form(
            step_id="remove_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): selector.BooleanSelector(),
                }
            ),
            description_placeholders={"entry": label},
        )

    async def async_step_import_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            file_id = user_input.get("import_yaml")
            if not file_id:
                errors["import_yaml"] = "required"
            else:
                try:
                    content = await self.hass.async_add_executor_job(
                        _read_uploaded_text, self.hass, file_id
                    )
                    new_addresses, parse_error = parse_addresses_yaml(content)
                    if parse_error:
                        errors["base"] = parse_error
                    else:
                        _LOGGER.info(
                            "YAML import OK — saving %d entries",
                            len(new_addresses),
                        )
                        await self._save_and_reload(new_addresses)
                        return self._finish_options()
                except Exception as err:
                    _LOGGER.exception("YAML import failed: %s", err)
                    errors["base"] = "invalid_yaml"

        return self.async_show_form(
            step_id="import_yaml",
            data_schema=vol.Schema(
                {
                    vol.Required("import_yaml"): selector.FileSelector(
                        selector.FileSelectorConfig(accept=".yaml,.yml")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_download_yaml_template(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return await self.async_step_init()

        template = _yaml_template()
        template_b64 = base64.b64encode(template.encode("utf-8")).decode("ascii")
        template_link = (
            f"[Download YAML template]"
            f"(data:text/yaml;base64,{template_b64})"
        )
        return self.async_show_form(
            step_id="download_yaml_template",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "template",
                        default=template,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiline=True,
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                }
            ),
            description_placeholders={
                "template": template_link,
            },
        )
