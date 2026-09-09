# B-Logicx for Home Assistant

Custom integration for the **B-Logicx (BL-NWM)** bus gateway: switches, covers, Sfeer, read-only addresses, RTC clock sync, LDM light sensors, TSM thermostat telemetry, SoftM virtual status tracking, and an optional TCP bus repeater.

**0.9.5.4:** SoftM `softm_timer` no longer cancelled by SoftM’s own Set echoes (Timer start / Status reply); Status mid-timer leaves the countdown running.

**0.9.5.3:** Bus repeater allows localhost; `blxmonitor` lives in the library package (avoids stdlib `select` shadow); timestamps include the date (`YYYY-MM-DD HH:MM:SS.mmm`).

**0.9.5.2:** `blxmonitor` `-l`/`--log-file` appends every on-screen TX/RX line (with timestamps) for rare-event debugging under `screen`/`tmux` via the TCP bus repeater.

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

After install, configure addresses in the integration options (UI) or import YAML. A template is included at:

`custom_components/b_logicx/template.yaml`

## Manual install (without HACS)

Copy the `custom_components/b_logicx` folder into your HA `config/custom_components/` directory, restart, then add the integration as above.

## SoftM status tracking (v0.9+)

Home Assistant can act as a **virtual status module** for Software Members (SoftM):

- Bus **Toggle** → flip memory and emit **Set** / **Reset** (cancels SoftM timer)
- Bus **Status** → reply with **Set** / **Reset** from memory (**does not** cancel SoftM timer)
- Optional bus **Timer** command → **Set**, wait `softm_timer` seconds, then **Reset** (`softm_timer` is not HA auto-off)
- External / HA **Set** / **Reset** update memory and cancel SoftM timer (SoftM’s own reply echoes do not)

Enable both:

1. **Integration settings** → *Enable SoftM status tracking*
2. Per address: `enable_softm_status_tracking: true` (and optional `softm_timer`, `persist_state`, `default_state`)

Do **not** combine SoftM tracking with `check_status` on the same address (YAML/UI reject that). Do **not** enable SoftM tracking if a hardware BL-STA already tracks that SoftM. SoftM-tracked addresses **must** use `on_command: Set` and `off_command: Reset` — Toggle (or any other command) is rejected in both YAML import and the config flow (VSM already answers bus Toggle; HA Toggle would double-flip).

## TCP bus repeater (v0.9)

BL-NWM / BL-NMX accept **one** TCP client. With the repeater enabled, HA keeps that single link and listens on HA (default port `10001`) so **BLConfig** / **blxmonitor** on the same LAN subnet as the NWM can share the bus.

1. **Integration settings** → *Enable TCP bus repeater* (port default `10001`)
2. Point BLConfig / blxmonitor at the **Home Assistant IP**, not the gateway IP (or `127.0.0.1` when running on the HA host itself)

Clients outside the NWM’s /24 are rejected, except **localhost** (loopback), which is always allowed. Raw RX (including Program traffic) is teed to clients; client TX is forwarded under the hub request lock.

Without the repeater you still need a second NWM/NWX or a BL-NWM2 to run HA and BLConfig at the same time.

## Diagnostics

`blxmonitor.py` (bus monitor / sender) lives in the shared library package (not next to HA platforms like `select.py`, which would shadow the stdlib):

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-or-gateway-ip> -p 10001
```

A thin wrapper at `.../b_logicx/blxmonitor.py` still re-execs that path for older commands.

Program traffic is shown by default; use `--hide-program` to filter it. With the bus repeater enabled, use the Home Assistant host as `-i`.

To capture every on-screen TX/RX line (with timestamps) for rare-event debugging:

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-or-gateway-ip> -p 10001 -l /config/blxbus.log
```

Lines are appended (same format as the terminal). Useful when leaving `blxmonitor` running under `screen`/`tmux` via the TCP bus repeater.

Using normal B-Logicx gateways like BL-NWM/NWX you can only open a single connection!
While the integration is running, blxmonitor or the official BLConfig windows software needs a second connection, only available if you have BL-NWM2

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
