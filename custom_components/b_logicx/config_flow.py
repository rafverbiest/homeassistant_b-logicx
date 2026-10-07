"""The screens for adding the integration and for editing its addresses.

The first flow only asks for the gateway host and port. One host is one entry.
Configure then opens the options flow:

- Integration settings holds the SoftM master switch and the bus repeater.
- Add picks a type, then opens that type's own screen.
- Edit and remove pick an existing address. Edit reuses the add screen.
- Import YAML overwrites the address list, but does not change the settings above.
- Export and the template show the text and a download link.

Saving an address writes the entry data and reloads. Leaving the menu writes
the options dict back unchanged, so closing it does not clear the SoftM
switch or the repeater.

Shared form helpers live in flow/common.py. Each address type lives in
flow/: rlm, softm, aud, readonly, ldm, tsm, rtc, shutter, and sfeer.
This file keeps setup, the menu, settings, edit, remove, and YAML.
"""

from __future__ import annotations

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
    parse_addresses_yaml,
)
from .const import *
from .flow.aud import AudSteps
from .flow.common import (
    _download_link,
    _entry_key,
    _entry_label,
    _find_entry,
    _picker_options,
    _placeholders,
    _upsert_by_key,
    _yaml_template,
)
from .flow.ldm import LdmSteps
from .flow.readonly import ReadonlySteps
from .flow.rlm import RlmSteps
from .flow.rtc import RtcSteps
from .flow.sfeer import SfeerSteps
from .flow.shutter import ShutterSteps
from .flow.softm import SoftmSteps
from .flow.tsm import TsmSteps

_LOGGER = logging.getLogger(__name__)


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


class BLogicxOptionsFlow(
    SfeerSteps,
    ShutterSteps,
    RtcSteps,
    TsmSteps,
    LdmSteps,
    ReadonlySteps,
    AudSteps,
    SoftmSteps,
    RlmSteps,
    OptionsFlowWithConfigEntry,
):
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
        """Main options screen.

        ``menu_options`` is the list of step ids. Home Assistant labels
        each one from ``options.step.init.menu_options`` in the viewer's
        language.
        """
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

        return self.async_show_menu(
            step_id="init",
            menu_options=keys,
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
        """Replace the address being edited, or add this one, then reload."""
        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        edit_key = getattr(self, "_edit_key", None)
        if edit_key:
            addresses = [a for a in addresses if _entry_key(a) != edit_key]
            self._edit_key = None
        addresses = _upsert_by_key(addresses, new_addr)
        await self._save_and_reload(addresses)
        return self._finish_options()

    def _take_edit_defaults(self) -> dict:
        """Defaults for the form edit just opened. Cleared so the next add is blank."""
        defaults = getattr(self, "_edit_defaults", {}) or {}
        self._edit_defaults = None
        return defaults

    async def async_step_add_address(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask which type, then open that type's screen. The default is RLM."""
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
                            options=[
                                ADDRESS_TYPE_RLM,
                                ADDRESS_TYPE_SOFTM,
                                ADDRESS_TYPE_AUD,
                                ADDRESS_TYPE_READONLY,
                                ADDRESS_TYPE_SHUTTER,
                                ADDRESS_TYPE_RTC,
                                ADDRESS_TYPE_LDM,
                                ADDRESS_TYPE_TSM,
                            ],
                            # selector.address_type.options, viewer's language.
                            translation_key="address_type",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(),
        )

    async def async_step_edit_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick an address and open the add screen for its type, filled in."""
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
        """Pick an address, then ask for confirmation before deleting it."""
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
        """Delete the picked address when the box is checked."""
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
        """Replace every address from an uploaded YAML file."""
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
            # The visible words are the two arguments below. An <a> tag
            # cannot live in the translation files, so the anchor is built here.
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
        """Show template.yaml and a link that downloads it in a new tab."""
        if user_input is not None:
            return await self.async_step_init()

        from .yaml_download import async_yaml_download_url

        try:
            template = _yaml_template()
        except FileNotFoundError:
            _LOGGER.error("B-Logicx template.yaml was not found")
            return self.async_show_form(
                step_id="download_yaml_template",
                data_schema=vol.Schema({}),
                errors={"base": "template_missing"},
                description_placeholders=_placeholders(),
            )

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
