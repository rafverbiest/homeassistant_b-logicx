"""Have the 'export YAML' function provide a browser-downloadable file

It's a bit of a hack, if anyone has a better idea, let me know :)

A data: URL is stripped by the config-flow markdown sanitizer. A normal
markdown link to this host is treated as an in-app route, so the dialog
closes and the main page opens. The flow therefore puts an HTML anchor, with
target="_blank", into the download_link placeholder. The translation strings
only contain that placeholder. An <a> tag written in strings.json is rejected
as an invalid tag.

requires_auth is false, and this view does not check the signature on the
URL. The id is a random value. The store forgets every staged file once more
than 32 are waiting. It does not expire them by the 15 minute signature time.
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
    """Return one staged YAML file. An unknown id is a 404."""

    url = "/api/b_logicx/yaml_download/{download_id}"
    name = "api:b_logicx:yaml_download"
    requires_auth = False

    async def get(self, request: web.Request, download_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        store: dict[str, Any] = hass.data.get(DOMAIN, {}).get(_DOWNLOADS_KEY, {})
        item = store.get(download_id)
        if item is None:
            return web.Response(status=404, text="Download expired or unknown")
        filename = item["filename"]
        content: str = item["content"]
        return web.Response(
            text=content,
            content_type="application/yaml",
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
    """Store the YAML and return a path the options flow can put in the anchor.

    The path is signed for 15 minutes. This view does not check that signature.
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
