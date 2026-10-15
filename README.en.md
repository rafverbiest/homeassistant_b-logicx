# B-Logicx for Home Assistant

[Nederlands](README.md) | **English**

Custom integration for the **[B-Logicx](https://b-logicx.be/) (NWM / NWX)** bus gateway: RLM's, dimmers, covers, sfeer (moods), read-only addresses, SoftM VSM, RTC, LDM/TSM/WSM, BM8, and a TCP bus repeater. Independent of the manufacturer.

**B-Logicx:** [b-logicx.be](https://b-logicx.be/) ·
**Site:** [b-logicx.rafverbiest.be](https://b-logicx.rafverbiest.be/en.html) ·
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

Configure addresses in the integration options (UI) or via YAML import. Template: `custom_components/b_logicx/flow/template.yaml`.

## Manual install

Copy `custom_components/b_logicx` into your HA `config/custom_components/`, restart, then add the integration as above.

## Further reading

- [Installation](https://b-logicx.rafverbiest.be/Installation.html) · [Configuration](https://b-logicx.rafverbiest.be/Configuration.html)
- [Dimmer](https://b-logicx.rafverbiest.be/Dimmer-en.html) · [SoftM](https://b-logicx.rafverbiest.be/SoftM-en.html) · [Bus repeater](https://b-logicx.rafverbiest.be/Bus-repeater-en.html)
- [Diagnostics](https://b-logicx.rafverbiest.be/Diagnostics.html) (`blxmonitor`) · [YAML](https://b-logicx.rafverbiest.be/YAML-en.html) · [B-Logicx upgrades](https://b-logicx.rafverbiest.be/Alternatives.html)

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
