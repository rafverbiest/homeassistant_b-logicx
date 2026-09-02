# B-Logicx for Home Assistant

Custom integration for the **B-Logicx (BL-NWM)** bus gateway: switches, covers, Sfeer moods, EXU inputs, RTC clock sync, LDM light sensors, and TSM thermostat telemetry.

## Install with HACS (custom repository)

GitHub hosting is enough — no extra server required.

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

After install, configure addresses in the integration options (UI) or import YAML. A template is included at:

`custom_components/b_logicx/template.yaml`

## Manual install (without HACS)

Copy the `custom_components/b_logicx` folder into your HA `config/custom_components/` directory, restart, then add the integration as above.

## Diagnostics

`blxmonitor.py` (bus monitor / sender) ships with the integration:

```bash
python3 /config/custom_components/b_logicx/blxmonitor.py -i <gateway-ip> -p 10001
```

Program traffic is shown by default; use `--hide-program` to filter it.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

See `TESTS.md` and `RELEASING.md`. Design history: `DESIGN.md`.

## License

See `LICENSE`.
