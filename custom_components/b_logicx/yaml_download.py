"""Short-lived signed YAML downloads for the options flow.

HA's config-flow markdown sanitizer strips ``data:`` URLs, so template/export
\"download\" links never worked. We serve the file via a signed API path instead.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_DOWNLOADS_KEY = "yaml_downloads"
_VIEW_KEY = "yaml_download_view_registered"
_TTL = timedelta(minutes=15)


class BLogicxYamlDownloadView(HomeAssistantView):
    """Serve a previously staged YAML blob (auth via signed path)."""

    url = "/api/b_logicx/yaml_download/{download_id}"
    name = "api:b_logicx:yaml_download"
    requires_auth = False  # signature on the URL is the gate

    async def get(self, request: web.Request, download_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        store: dict[str, Any] = hass.data.get(DOMAIN, {}).get(_DOWNLOADS_KEY, {})
        item = store.get(download_id)
        if item is None:
            return web.Response(status=404, text="Download expired or unknown")
        filename = item["filename"]
        content: str = item["content"]
        return web.Response(
            body=content.encode("utf-8"),
            content_type="application/yaml; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )


def async_setup_yaml_downloads(hass: HomeAssistant) -> None:
    """Register the download view once per HA instance."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(_DOWNLOADS_KEY, {})
    if domain_data.get(_VIEW_KEY):
        return
    hass.http.register_view(BLogicxYamlDownloadView)
    domain_data[_VIEW_KEY] = True
    _LOGGER.debug("Registered B-Logicx YAML download API view")


def async_yaml_download_url(
    hass: HomeAssistant,
    *,
    filename: str,
    content: str,
) -> str:
    """Stage YAML and return a signed relative path for a markdown link.

    Link *labels* belong in ``strings.json`` / ``translations/*.json``; this
    helper only returns the URL placeholder value (e.g. ``{download_url}``).
    """
    async_setup_yaml_downloads(hass)
    download_id = uuid.uuid4().hex
    store: dict[str, Any] = hass.data[DOMAIN][_DOWNLOADS_KEY]
    # Drop stale entries (keep store small)
    if len(store) > 32:
        store.clear()
    store[download_id] = {"filename": filename, "content": content}
    path = f"/api/b_logicx/yaml_download/{download_id}"
    return async_sign_path(hass, path, _TTL)
