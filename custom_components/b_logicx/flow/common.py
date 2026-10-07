"""Helpers shared by the options screens.

Placeholders, the download anchor, and the edit/remove keys live here so
each address type can move to its own file without copying them.
"""

from __future__ import annotations

import html
from typing import Any

from homeassistant.helpers import selector

from ..address_config import entries_sorted_for_picker, entry_label
from ..const import *

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
    data.update({k: str(v) for k, v in kwargs.items()})
    return data


def _command_selector(options: list[str], default: str) -> Any:
    """Dropdown of command names such as Set, Reset, and Toggle."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=c, label=c) for c in options],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


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
    """The address whose edit key matches, or None."""
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


def _yaml_template() -> str:
    """Read template.yaml next to this file."""
    from pathlib import Path

    path = Path(__file__).resolve().parent / "template.yaml"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        raise FileNotFoundError(path) from err
