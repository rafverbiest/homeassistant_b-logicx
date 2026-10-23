# Thank you to jeroendw88 (https://github.com/jeroendw88/bhs-homeassistant) for providing member types and example JSON data!
# API: https://b-logicx.be/Software/BHS/API_Docs/index.html
"""Options steps: import bus members from the BHS once."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..address_config import normalize_yaml_entry
from ..b_logicx.bhs_client import (
    BHS_DEFAULT_PORT,
    BhsApiError,
    BhsBlockedError,
    BhsClient,
    BhsConnectionError,
    BhsPendingError,
    BhsSecuredError,
    ClassifyResult,
    ImportCandidate,
    SecureSample,
    classify_members,
    format_secure_dump,
    generate_device_credentials,
    public_pem_from_private,
    read_member_list,
)
from ..b_logicx.detect import configured_bus_keys
from ..const import *
from .common import _flow_lang, _placeholders

_LOGGER = logging.getLogger(__name__)


class BhsSteps:
    """Options steps for Import from BHS. Mixed into BLogicxOptionsFlow."""

    async def async_step_import_bhs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Host and port of the BHS PC."""
        errors: dict[str, str] = {}
        defaults = getattr(self, "_bhs_form", {}) or {}
        if user_input is not None:
            host = str(user_input.get("host") or "").strip()
            try:
                port = int(user_input.get("port") or BHS_DEFAULT_PORT)
            except (TypeError, ValueError):
                port = 0
            self._bhs_form = {"host": host, "port": port or BHS_DEFAULT_PORT}
            reuse = True
            if self._bhs_has_stored_key():
                reuse = bool(user_input.get("reuse_key", True))
            if not host:
                errors["host"] = "required"
            elif not 1 <= port <= 65535:
                errors["port"] = "required"
            else:
                try:
                    outcome = await self._bhs_fetch(host, port, reuse=reuse)
                except BhsConnectionError:
                    errors["base"] = "cannot_connect"
                except BhsSecuredError:
                    errors["base"] = "bhs_secured"
                except BhsBlockedError:
                    await self._clear_bhs_creds()
                    errors["base"] = "bhs_blocked"
                except BhsPendingError:
                    return await self.async_step_import_bhs_pending()
                except BhsApiError:
                    _LOGGER.exception("BHS import request failed")
                    errors["base"] = "bhs_error"
                except Exception:
                    _LOGGER.exception("BHS import failed")
                    errors["base"] = "bhs_error"
                else:
                    if outcome == "pending":
                        return await self.async_step_import_bhs_pending()
                    if outcome == "secured":
                        return await self.async_step_import_bhs_secured()
                    return await self.async_step_import_bhs_pick()
        fields: dict[Any, Any] = {
            vol.Required("host", default=str(defaults.get("host") or "")): str,
            vol.Required(
                "port",
                default=int(defaults.get("port") or BHS_DEFAULT_PORT),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        }
        if self._bhs_has_stored_key():
            fields[vol.Required("reuse_key", default=True)] = selector.BooleanSelector()
        return self.async_show_form(
            step_id="import_bhs",
            data_schema=vol.Schema(fields),
            errors=errors or None,
            description_placeholders=_placeholders(),
        )

    async def async_step_import_bhs_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """BLConfig has to approve the Home Assistant device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            form = getattr(self, "_bhs_form", None) or {}
            host = str(form.get("host") or "").strip()
            port = int(form.get("port") or BHS_DEFAULT_PORT)
            if not host:
                return await self.async_step_import_bhs()
            try:
                outcome = await self._bhs_fetch(host, port, reuse=True)
            except BhsPendingError:
                errors["base"] = "pending_approval"
            except BhsSecuredError:
                errors["base"] = "bhs_secured"
            except BhsBlockedError:
                await self._clear_bhs_creds()
                errors["base"] = "bhs_blocked"
            except BhsConnectionError:
                errors["base"] = "cannot_connect"
            except BhsApiError:
                _LOGGER.exception("BHS import request failed")
                errors["base"] = "bhs_error"
            except Exception:
                _LOGGER.exception("BHS import failed")
                errors["base"] = "bhs_error"
            else:
                if outcome == "pending":
                    errors["base"] = "pending_approval"
                elif outcome == "secured":
                    return await self.async_step_import_bhs_secured()
                else:
                    return await self.async_step_import_bhs_pick()
        return self.async_show_form(
            step_id="import_bhs_pending",
            data_schema=vol.Schema({}),
            errors=errors or None,
            description_placeholders=_placeholders(),
        )

    async def async_step_import_bhs_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Checkboxes for members this integration can store."""
        classified: ClassifyResult = getattr(self, "_bhs_classified", None) or ClassifyResult()
        by_key: dict[str, ImportCandidate] = {
            item.key: item for item in classified.candidates
        }
        if user_input is not None:
            selected = user_input.get("members") or []
            if isinstance(selected, str):
                selected = [selected]
            addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
            added = 0
            for key in selected:
                item = by_key.get(str(key))
                if item is None:
                    continue
                try:
                    entry = normalize_yaml_entry(item.entry)
                except ValueError:
                    _LOGGER.exception("BHS import skipped an invalid member")
                    continue
                addresses.append(entry)
                added += 1
            if added:
                await self._save_and_reload(addresses)
            self._bhs_added = added
            return await self.async_step_import_bhs_done()

        if not classified.candidates:
            self._bhs_added = 0
            return await self.async_step_import_bhs_done()

        options = [
            selector.SelectOptionDict(value=item.key, label=item.label)
            for item in classified.candidates
        ]
        return self.async_show_form(
            step_id="import_bhs_pick",
            data_schema=vol.Schema(
                {
                    vol.Optional("members", default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders=_placeholders(
                already=self._bhs_block(classified.already, "already"),
                leftover=self._bhs_block(classified.leftover, "leftover"),
            ),
        )

    async def async_step_import_bhs_secured(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Secured BHS: the sample file is written and nothing is imported."""
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="import_bhs_secured",
            data_schema=vol.Schema({}),
            description_placeholders=_placeholders(
                path=str(getattr(self, "_bhs_secure_path", "")),
            ),
        )

    async def async_step_import_bhs_done(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """How many were added, then the options menu."""
        if user_input is not None:
            return await self.async_step_init()
        classified: ClassifyResult = getattr(self, "_bhs_classified", None) or ClassifyResult()
        added = int(getattr(self, "_bhs_added", 0) or 0)
        leftover_text = "\n".join(classified.leftover) if classified.leftover else ""
        return self.async_show_form(
            step_id="import_bhs_done",
            data_schema=vol.Schema({}),
            description_placeholders=_placeholders(
                added=str(added),
                already_count=str(len(classified.already)),
                leftover_count=str(len(classified.leftover)),
                leftover=leftover_text,
            ),
        )

    def _bhs_block(self, lines: list[str], kind: str) -> str:
        if not lines:
            return ""
        if kind == "already":
            header = (
                "Already in Home Assistant:"
                if _flow_lang(self.hass) != "nl"
                else "Al in Home Assistant:"
            )
        else:
            header = (
                "Not imported:"
                if _flow_lang(self.hass) != "nl"
                else "Niet geïmporteerd:"
            )
        return header + "\n" + "\n".join(lines)

    async def _persist_bhs_creds(
        self, device_id: str, private_pem: str, public_pem: str
    ) -> None:
        options = {
            **self.config_entry.options,
            CONF_BHS_DEVICE_ID: device_id,
            CONF_BHS_PRIVATE_KEY: private_pem,
            CONF_BHS_PUBLIC_KEY: public_pem,
        }
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )

    async def _clear_bhs_creds(self) -> None:
        options = dict(self.config_entry.options)
        options.pop(CONF_BHS_DEVICE_ID, None)
        options.pop(CONF_BHS_PRIVATE_KEY, None)
        options.pop(CONF_BHS_PUBLIC_KEY, None)
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )

    def _bhs_has_stored_key(self) -> bool:
        options = self.config_entry.options
        return bool(
            str(options.get(CONF_BHS_DEVICE_ID) or "").strip()
            and str(options.get(CONF_BHS_PRIVATE_KEY) or "").strip()
        )

    async def _bhs_fetch(self, host: str, port: int, *, reuse: bool = True) -> str:
        """Register if needed, then read members or save a secured sample.

        Returns ``pending`` when BLConfig still has to approve the device,
        and ``secured`` when ISSECURE is on. A secured read writes the
        sample and does not classify. ``reuse`` false mints a new key pair
        even when one is already stored. A later Continue reuses whatever
        was just stored, so it does not register a second device.
        """
        session = async_get_clientsession(self.hass)
        device_id = str(
            self.config_entry.options.get(CONF_BHS_DEVICE_ID) or ""
        ).strip()
        private_pem = str(
            self.config_entry.options.get(CONF_BHS_PRIVATE_KEY) or ""
        ).strip()
        public_pem = str(
            self.config_entry.options.get(CONF_BHS_PUBLIC_KEY) or ""
        ).strip()
        stored = bool(reuse and device_id and private_pem)
        if stored and not public_pem:
            try:
                public_pem = await self.hass.async_add_executor_job(
                    public_pem_from_private, private_pem
                )
                await self._persist_bhs_creds(device_id, private_pem, public_pem)
            except Exception:
                _LOGGER.exception("Stored BHS private key could not be read")
                stored = False
                device_id = ""
                private_pem = ""
                public_pem = ""
        if not stored:
            device_id, private_pem, public_pem = (
                await self.hass.async_add_executor_job(generate_device_credentials)
            )
            await self._persist_bhs_creds(device_id, private_pem, public_pem)

        client = BhsClient(session, host, port, device_id)
        if not stored:
            status = await client.register(public_pem)
            if status == "Pending":
                return "pending"
        try:
            return await self._bhs_read(client, host, port, device_id, private_pem)
        except BhsApiError as err:
            if err.status == 401 and stored:
                await self._clear_bhs_creds()
                device_id, private_pem, public_pem = (
                    await self.hass.async_add_executor_job(
                        generate_device_credentials
                    )
                )
                await self._persist_bhs_creds(device_id, private_pem, public_pem)
                client = BhsClient(session, host, port, device_id)
                status = await client.register(public_pem)
                if status == "Pending":
                    return "pending"
                return await self._bhs_read(
                    client, host, port, device_id, private_pem
                )
            raise

    async def _bhs_read(
        self,
        client: BhsClient,
        host: str,
        port: int,
        device_id: str,
        private_pem: str,
    ) -> str:
        """Classify a cleartext list, or write the secured sample and stop."""
        loaded = await read_member_list(client)
        if isinstance(loaded, SecureSample):
            text = format_secure_dump(
                host=host,
                port=port,
                device_id=device_id,
                private_pem=private_pem,
                sample=loaded,
            )
            self._bhs_secure_path = await self._write_bhs_secure_file(text)
            return "secured"
        addresses = list(self.config_entry.data.get(CONF_ADDRESSES, []))
        self._bhs_classified = classify_members(
            loaded,
            configured_bus_keys(addresses),
            lang=_flow_lang(self.hass),
        )
        return "ok"

    async def _write_bhs_secure_file(self, text: str) -> str:
        path = Path(self.hass.config.path) / "b_logicx_bhs_secure.txt"

        def _write() -> None:
            # newline="" keeps the CRLF inside the BHS blob as sent.
            path.write_text(text, encoding="utf-8", newline="")

        await self.hass.async_add_executor_job(_write)
        _LOGGER.info("Wrote secured BHS sample to %s", path)
        return str(path)
