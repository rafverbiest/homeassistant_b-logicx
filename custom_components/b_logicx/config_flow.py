"""Config flow and options flow for B-Logicx integration."""

from __future__ import annotations

import base64
import html
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

from .bus_repeater import suggested_repeater_cidr
from .address_config import (
    dump_addresses_yaml,
    entries_sorted_for_picker,
    entry_label,
    parse_addresses_yaml,
)
from .const import (
    ADDRESS_TYPE_AUD,
    ADDRESS_TYPE_READONLY,
    ADDRESS_TYPE_LDM,
    ADDRESS_TYPE_RLM,
    ADDRESS_TYPE_RTC,
    ADDRESS_TYPE_SFEER,
    ADDRESS_TYPE_SHUTTER,
    ADDRESS_TYPE_SOFTM,
    ADDRESS_TYPE_TSM,
    CONF_ADDRESSES,
    CONF_BUS_REPEATER_ALLOW,
    CONF_BUS_REPEATER_ENABLED,
    CONF_BUS_REPEATER_PORT,
    CONF_PORT,
    CONF_SOFTM_TRACKING_ENABLED,
    DEFAULT_AUD_GROUP,
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
    is_softm_address,
    next_sfeer_group,
    sfeer_room_group,
)

_LOGGER = logging.getLogger(__name__)

# Explicit labels for async_show_menu (dict form). Selector translation_key is
# unreliable in the options dialog and showed raw keys like add_address.
_MENU_LABELS_EN: dict[str, str] = {
    "add_address": "Add bus address",
    "add_sfeer_room": "Add Sfeer room",
    "add_sfeer_mood": "Add Sfeer",
    "edit_select": "Edit entry",
    "remove_select": "Remove entry",
    "integration_settings": "Integration settings",
    "export_yaml": "Export YAML",
    "download_yaml_template": "Download YAML template",
    "import_yaml": "Import from YAML",
}
_MENU_LABELS_NL: dict[str, str] = {
    "add_address": "Busadres toevoegen",
    "add_sfeer_room": "Sfeer-ruimte toevoegen",
    "add_sfeer_mood": "Sfeer toevoegen",
    "edit_select": "Item bewerken",
    "remove_select": "Item verwijderen",
    "integration_settings": "Integratie-instellingen",
    "export_yaml": "YAML exporteren",
    "download_yaml_template": "YAML-sjabloon downloaden",
    "import_yaml": "Importeren uit YAML",
}

# Empty defaults so FormatJS never throws MISSING_VALUE for cached templates
# that still reference old placeholders ({addresses}, {example}, {step_title}, …).
_SAFE_PLACEHOLDERS: dict[str, str] = {
    "addresses": "",
    "entry_count": "",
    "example": "",
    "warning": "",
    "moods": "",
    "room_name": "",
    "group": "",
    "template": "",
    "export_link": "",
    "download_url": "",
    "download_link": "",
    "entry": "",
    "intro": "",
    "step_title": "",
    "step_body": "",
}

_ADDRESS_TYPE_LABELS_EN: dict[str, str] = {
    ADDRESS_TYPE_RLM: "Switch (RLM)",
    ADDRESS_TYPE_SOFTM: "SoftM (software member)",
    ADDRESS_TYPE_AUD: "BL-AUD (audio module)",
    ADDRESS_TYPE_READONLY: "Read-only address (observe only, no control)",
    ADDRESS_TYPE_SHUTTER: "Cover / roller / shutter (open + close addresses)",
    ADDRESS_TYPE_RTC: "RTC (bus clock)",
    ADDRESS_TYPE_LDM: "LDM (light sensor)",
    ADDRESS_TYPE_TSM: "TSM (temperature / thermostat)",
}
_ADDRESS_TYPE_LABELS_NL: dict[str, str] = {
    ADDRESS_TYPE_RLM: "Schakelaar (RLM)",
    ADDRESS_TYPE_SOFTM: "SoftM (software member)",
    ADDRESS_TYPE_AUD: "BL-AUD (audiomodule)",
    ADDRESS_TYPE_READONLY: "Alleen-lezen adres (alleen volgen, geen bediening)",
    ADDRESS_TYPE_SHUTTER: "Rolluik (open- + sluitadres)",
    ADDRESS_TYPE_RTC: "RTC (busklok)",
    ADDRESS_TYPE_LDM: "LDM (lichtsensor)",
    ADDRESS_TYPE_TSM: "TSM (temperatuur / thermostaat)",
}


def _flow_lang(hass: Any) -> str:
    return (getattr(getattr(hass, "config", None), "language", None) or "en")[:2]


def _download_link(hass: Any, url: str, label_en: str, label_nl: str) -> str:
    """Anchor for a config-flow description.

    The translation string must not contain ``<a ...>``: IntlMessageFormat
    reports that as an invalid tag. A markdown link is same-origin, and the
    frontend then navigates inside the app instead of downloading. Passing
    the anchor as a placeholder keeps the translator happy and sets
    ``target="_blank"`` so the click is a real download.
    """
    label = label_nl if _flow_lang(hass) == "nl" else label_en
    return (
        f'<a href="{html.escape(url, quote=True)}" target="_blank">'
        f"{html.escape(label)}</a>"
    )


def _placeholders(**kwargs: Any) -> dict[str, str]:
    """Merge safe empty defaults with real dynamic values for a form/menu."""
    data = dict(_SAFE_PLACEHOLDERS)
    # Also clear any lbl_* leftovers from the reverted placeholder-title hack
    data.update({k: str(v) for k, v in kwargs.items()})
    return data


def _address_type_options(hass: Any) -> list[selector.SelectOptionDict]:
    labels = (
        _ADDRESS_TYPE_LABELS_NL
        if _flow_lang(hass) == "nl"
        else _ADDRESS_TYPE_LABELS_EN
    )
    order = [
        ADDRESS_TYPE_RLM,
        ADDRESS_TYPE_SOFTM,
        ADDRESS_TYPE_AUD,
        ADDRESS_TYPE_READONLY,
        ADDRESS_TYPE_SHUTTER,
        ADDRESS_TYPE_RTC,
        ADDRESS_TYPE_LDM,
        ADDRESS_TYPE_TSM,
    ]
    return [
        selector.SelectOptionDict(value=v, label=labels.get(v, v)) for v in order
    ]


def _command_selector(options: list[str], default: str) -> Any:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=c, label=c) for c in options],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _menu_label(hass: Any, key: str) -> str:
    """Human label for a main-menu action (NL/EN), never the raw step id."""
    loc_key = f"component.{DOMAIN}.selector.options_menu.options.{key}"
    try:
        text = hass.localize(loc_key)
        if text and text not in (loc_key, key) and f".{key}" not in text:
            return text
    except Exception:  # noqa: BLE001
        pass
    table = _MENU_LABELS_NL if _flow_lang(hass) == "nl" else _MENU_LABELS_EN
    return table.get(key, _MENU_LABELS_EN.get(key, key))


def _entry_key(entry: dict) -> str:
    """Stable key for edit/remove menus."""
    t = entry.get("type")
    if t == ADDRESS_TYPE_SHUTTER:
        return (
            f"cover:{entry['open_group']}.{entry['open_address']}"
            f":{entry['close_group']}.{entry['close_address']}"
        )
    if t == ADDRESS_TYPE_SFEER:
        return f"sfeer:{entry.get('name', '')}"
    return f"addr:{entry['group']}.{entry['address']}"


def _entry_label(entry: dict) -> str:
    """Picker label: bus address first (matches sort), then name."""
    return entry_label(entry)


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
    # Single-address entries also match by group+address across type changes
    t = new_entry.get("type")
    if t in (
        ADDRESS_TYPE_RLM,
        ADDRESS_TYPE_SOFTM,
        ADDRESS_TYPE_AUD,
        ADDRESS_TYPE_READONLY,
    ):
        for i, addr in enumerate(addresses):
            if addr.get("type") in (
                ADDRESS_TYPE_RLM,
                ADDRESS_TYPE_SOFTM,
                ADDRESS_TYPE_AUD,
                ADDRESS_TYPE_READONLY,
                None,
            ):
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
# Types: rlm | softm | aud | shutter | sfeer | readonly | rtc | ldm | tsm

addresses:
  - type: rlm
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
    group: 5
    check_status: true
    moods:
      - name: Reading
        address: 221
      - name: Cinema
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

  - type: softm
    name: Software Member Example
    group: 10
    address: 200
    on_command: Set
    off_command: Reset
    enable_softm_status_tracking: true
    persist_state: true
    default_state: false

  - type: aud
    name: Living audio
    group: 4
    address: 1
    source_1: Radio
    source_2: Source 2
    source_3: Source 3
    source_4: Source 4
    source_5: Source 5
    source_6: Source 6
    source_7: Source 7
    source_8: Source 8
"""


class BLogicxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for B-Logicx (gateway IP)."""

    VERSION = 5

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
        """Main options screen: polished action list (async_show_menu dict)."""
        current = self.config_entry.data.get(CONF_ADDRESSES, [])
        keys: list[str] = [
            "add_address",
            "add_sfeer_room",
        ]
        if any(a.get("type") == ADDRESS_TYPE_SFEER for a in current):
            keys.append("add_sfeer_mood")
        if current:
            keys.extend(["edit_select", "remove_select"])
        keys.extend(
            [
                "integration_settings",
                "export_yaml",
                "download_yaml_template",
                "import_yaml",
            ]
        )
        # Dict form → human labels in the list (never raw add_address keys)
        menu_options = {k: _menu_label(self.hass, k) for k in keys}

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders=_placeholders(),
        )

    async def async_step_integration_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """SoftM tracking master switch + TCP bus repeater."""
        if user_input is not None:
            allow = str(user_input.get(CONF_BUS_REPEATER_ALLOW) or "").strip()
            if allow:
                try:
                    allow = str(ipaddress.ip_network(allow, strict=False))
                except ValueError:
                    return self.async_show_form(
                        step_id="integration_settings",
                        data_schema=self._integration_settings_schema(
                            {
                                **self.config_entry.options,
                                **user_input,
                            }
                        ),
                        errors={"base": "invalid_subnet"},
                        description_placeholders=_placeholders(),
                    )
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
                CONF_BUS_REPEATER_ALLOW: allow,
            }
            return self.async_create_entry(title="", data=opts)

        return self.async_show_form(
            step_id="integration_settings",
            data_schema=self._integration_settings_schema(self.config_entry.options),
            description_placeholders=_placeholders(),
        )

    def _integration_settings_schema(self, opts: dict) -> vol.Schema:
        host = self.config_entry.data.get(CONF_HOST, "")
        allow_default = opts.get(CONF_BUS_REPEATER_ALLOW) or suggested_repeater_cidr(
            str(host)
        )
        return vol.Schema(
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
                        opts.get(CONF_BUS_REPEATER_PORT, DEFAULT_BUS_REPEATER_PORT)
                    ),
                ): int,
                vol.Optional(
                    CONF_BUS_REPEATER_ALLOW,
                    default=allow_default,
                ): str,
            }
        )

    async def _commit_address(self, new_addr: dict) -> FlowResult:
        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        edit_key = getattr(self, "_edit_key", None)
        if edit_key:
            addresses = [a for a in addresses if _entry_key(a) != edit_key]
            self._edit_key = None
        addresses = _upsert_by_key(addresses, new_addr)
        await self._save_and_reload(addresses)
        return self._finish_options()

    def _take_edit_defaults(self) -> dict:
        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return defaults

    async def async_step_add_address(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            t = user_input.get("address_type", ADDRESS_TYPE_RLM)
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
            if t == ADDRESS_TYPE_AUD:
                return await self.async_step_add_aud()
            if t == ADDRESS_TYPE_SOFTM:
                return await self.async_step_add_softm()
            return await self.async_step_add_rlm()

        return self.async_show_form(
            step_id="add_address",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address_type", default=ADDRESS_TYPE_RLM
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_address_type_options(self.hass),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(),
        )

    async def async_step_add_rlm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit an RLM switch. SoftM has its own screen."""
        if user_input is not None:
            new_addr: dict[str, Any] = {
                "name": user_input["name"].strip(),
                "type": ADDRESS_TYPE_RLM,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
                "on_command": user_input.get("on_command", DEFAULT_ON_COMMAND),
                "off_command": user_input.get("off_command", DEFAULT_OFF_COMMAND),
                "check_status": bool(user_input.get("check_status", False)),
                "enable_softm_status_tracking": False,
            }
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        return self.async_show_form(
            step_id="add_rlm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required("group", default=defaults.get("group", 2)): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Required(
                        "on_command",
                        default=defaults.get("on_command", DEFAULT_ON_COMMAND),
                    ): _command_selector(ON_COMMANDS, DEFAULT_ON_COMMAND),
                    vol.Required(
                        "off_command",
                        default=defaults.get("off_command", DEFAULT_OFF_COMMAND),
                    ): _command_selector(OFF_COMMANDS, DEFAULT_OFF_COMMAND),
                    vol.Optional(
                        "check_status",
                        default=defaults.get("check_status", False),
                    ): selector.BooleanSelector(),
                }
            ),
            description_placeholders=_placeholders(),
        )

    async def async_step_add_softm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a SoftM. Set/Reset only; VSM tracking is optional."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Absent means the box was cleared. The form default is on.
            vsm = bool(user_input.get("enable_softm_status_tracking", False))
            timer = user_input.get("softm_timer")
            timer_val: float | None = None
            if timer not in (None, "", 0, 0.0):
                timer_val = float(timer)
                if timer_val <= 0:
                    timer_val = None
            if timer_val and not vsm:
                errors["base"] = "softm_timer_needs_vsm"
            else:
                new_addr: dict[str, Any] = {
                    "name": user_input["name"].strip(),
                    "type": ADDRESS_TYPE_SOFTM,
                    "group": int(user_input["group"]),
                    "address": int(user_input["address"]),
                    "on_command": DEFAULT_ON_COMMAND,
                    "off_command": DEFAULT_OFF_COMMAND,
                    "check_status": False,
                    "enable_softm_status_tracking": vsm,
                    "persist_state": bool(user_input.get("persist_state", True)),
                    "default_state": bool(user_input.get("default_state", False)),
                }
                if timer_val:
                    new_addr["softm_timer"] = timer_val
                return await self._commit_address(new_addr)

        defaults = (
            user_input
            if user_input is not None
            else self._take_edit_defaults()
        )
        return self.async_show_form(
            step_id="add_softm",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=defaults.get("name", "")): str,
                    vol.Required(
                        "group", default=defaults.get("group", 10)
                    ): int,
                    vol.Required(
                        "address", default=defaults.get("address", 0)
                    ): int,
                    vol.Optional(
                        "enable_softm_status_tracking",
                        default=defaults.get("enable_softm_status_tracking", True),
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
            errors=errors,
            description_placeholders=_placeholders(),
        )

    async def async_step_add_aud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a BL-AUD media player and its eight source names."""
        if user_input is not None:
            new_addr: dict[str, Any] = {
                "name": user_input["name"].strip() or "Audio",
                "type": ADDRESS_TYPE_AUD,
                "group": int(user_input["group"]),
                "address": int(user_input["address"]),
            }
            for i in range(1, 9):
                key = f"source_{i}"
                label = str(user_input.get(key) or "").strip()
                new_addr[key] = label or f"Source {i}"
            return await self._commit_address(new_addr)

        defaults = self._take_edit_defaults()
        schema: dict[Any, Any] = {
            vol.Required("name", default=defaults.get("name", "Audio")): str,
            vol.Required(
                "group",
                default=int(defaults.get("group", DEFAULT_AUD_GROUP)),
            ): int,
            vol.Required(
                "address", default=int(defaults.get("address", 1))
            ): int,
        }
        for i in range(1, 9):
            key = f"source_{i}"
            schema[
                vol.Optional(key, default=defaults.get(key) or f"Source {i}")
            ] = str
        return self.async_show_form(
            step_id="add_aud",
            data_schema=vol.Schema(schema),
            description_placeholders=_placeholders(),
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
            ),
            description_placeholders=_placeholders(),
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
            ),
            description_placeholders=_placeholders(),
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
            ),
            description_placeholders=_placeholders(),
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
            ),
            description_placeholders=_placeholders(),
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
            description_placeholders=_placeholders(),
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
                or (
                    "(nog geen — gebruik Sfeer toevoegen)"
                    if _flow_lang(self.hass) == "nl"
                    else "(none yet — use Add Sfeer)"
                )
            )
        else:
            def_group = next_sfeer_group(used)
            def_name = ""
            def_check = False
            mood_desc = (
                "(nog geen — gebruik Sfeer toevoegen na het aanmaken van de ruimte)"
                if _flow_lang(self.hass) == "nl"
                else "(none yet — use Add Sfeer after creating the room)"
            )
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
            description_placeholders=_placeholders(moods=mood_desc),
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
                label=_entry_label(r),
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
            ),
            description_placeholders=_placeholders(),
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
            description_placeholders=_placeholders(room_name=str(room.get("name", "")),
                group=str(room_group),
            ),
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
            if t == ADDRESS_TYPE_AUD:
                return await self.async_step_add_aud()
            if t == ADDRESS_TYPE_SOFTM or is_softm_address(entry):
                return await self.async_step_add_softm()
            return await self.async_step_add_rlm()

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
            description_placeholders=_placeholders(),
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
            description_placeholders=_placeholders(),
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
            description_placeholders=_placeholders(entry=label),
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
            description_placeholders=_placeholders(),
        )

    async def async_step_export_yaml(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show current addresses as YAML (same format as import)."""
        if user_input is not None:
            return await self.async_step_init()

        from .yaml_download import async_yaml_download_url

        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        export_text = dump_addresses_yaml(
            addresses, options=dict(self.config_entry.options)
        )
        download_url = async_yaml_download_url(
            self.hass,
            filename="b_logicx_addresses.yaml",
            content=export_text,
        )
        return self.async_show_form(
            step_id="export_yaml",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "export",
                        default=export_text,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiline=True,
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                }
            ),
            # Link label lives in strings/nl.json; only the signed URL is dynamic.
            description_placeholders=_placeholders(
                download_link=_download_link(
                    self.hass,
                    download_url,
                    "Download YAML file",
                    "YAML-bestand downloaden",
                ),
            ),
        )

    async def async_step_download_yaml_template(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return await self.async_step_init()

        from .yaml_download import async_yaml_download_url

        template = _yaml_template()
        download_url = async_yaml_download_url(
            self.hass,
            filename="b_logicx_template.yaml",
            content=template,
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
            description_placeholders=_placeholders(
                download_link=_download_link(
                    self.hass,
                    download_url,
                    "Download template file",
                    "Sjabloon-bestand downloaden",
                ),
            ),
        )
