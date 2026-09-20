# B-Logicx for Home Assistant

[Nederlands](README.md) | **English**

Custom integration for the **B-Logicx (BL-NWM / BL-NWX)** bus gateway: switches, covers, Sfeer, read-only addresses, SoftM VSM, RTC, LDM/TSM, and an optional TCP bus repeater.

**Site:** [b-logicx.rafverbiest.be](https://b-logicx.rafverbiest.be/en.html) ·
**Wiki:** [documentation](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en) ·
**Releases:** [changelog](https://github.com/rafverbiest/homeassistant_b-logicx/releases)

## Install with HACS (custom repository)

1. Install [HACS](https://hacs.xyz/) if you do not already have it.
2. In Home Assistant open **HACS** → top-right **⋮** → **Custom repositories**.
3. Repository URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Category: **Integration**
4. Click **Add**, then find **B-Logicx** in HACS and **Download**.
5. **Restart** Home Assistant.
6. **Settings → Devices & services → Add integration → B-Logicx** and enter your gateway IP (default port `10001`).

Configure addresses in the integration options (UI) or via YAML import. Template: `custom_components/b_logicx/template.yaml`.

## Manual install

Copy `custom_components/b_logicx` into your HA `config/custom_components/`, restart, then add the integration as above.

## Further reading (wiki)

- [Installation](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installation) · [Configuration](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuration)
- [SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM-en) · [Bus repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater-en)
- [Diagnostics](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostics) (`blxmonitor`) · [YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML-en)

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

See `TESTS.md`, `RELEASING.md`, and `TRANSLATIONS.md`.

## License

See `LICENSE`.
