# Offline tests (v0.9)

These tests exercise the B-Logicx library and YAML config against an in-process
**FakeGateway** (TCP, same 2-byte datagram protocol as a real BL-NWM).  
They do **not** require Home Assistant or a physical gateway.

SoftM tracker + YAML SoftM fields: `tests/test_softm.py`. Bus repeater subnet
helper is covered there as well.

## Setup (once)

From the project root (`b_logicx/`):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Dependencies: `pytest`, `pytest-asyncio`, `PyYAML` (see `requirements-dev.txt`).

## Run all tests

```bash
pytest
```

Or with the venv python explicitly:

```bash
.venv/bin/python -m pytest
```

Quiet summary:

```bash
pytest -q
```

Verbose (one line per test):

```bash
pytest -v
```

Typical runtime is about **1–2 seconds** for the full suite.

## Bus log (blxmonitor-style)

FakeGateway records a chronological transcript in the same format as
`blxmonitor.py`:

```text
[16:29:23.660] [SENT] Status 2.80   # client → gateway
[16:29:23.660] Set 9.99             # gateway → client
[16:29:23.681] Set 2.80
```

| Mode | How |
|------|-----|
| **Quiet green runs** | Default — no bus lines |
| **Always dump on failure** | Automatic — no flag needed |
| **Live transcript** | `pytest --bus-log -s` |
| **Live via environment** | `BLX_BUS_LOG=1 pytest -s` |

### Examples

```bash
# Live bus log for all tests that use FakeGateway
pytest --bus-log -s

# Same, environment variable (accepted values: 1, true, yes, on)
BLX_BUS_LOG=1 pytest -s

# One adversarial scenario with live log
pytest tests/test_adversarial.py::test_interleaved_unsolicited_during_status --bus-log -s

# Log lines also go to the logger b_logicx.tests.bus (INFO)
pytest --log-cli-level=INFO --bus-log -s
```

`-s` disables pytest’s capture so lines appear immediately while the test runs.
Without `-s`, live prints may only show after each test finishes.

## Useful pytest options

| Option | Meaning |
|--------|---------|
| `-q` / `--quiet` | Less output |
| `-v` / `--verbose` | Per-test names |
| `-s` | No stdout capture (needed for live bus log) |
| `-k EXPR` | Run tests whose names match `EXPR` |
| `-x` | Stop on first failure |
| `--tb=short` | Shorter tracebacks |
| `--tb=line` | One-line tracebacks |
| `--lf` | Re-run only last failures |
| `--bus-log` | **Project option:** print blxmonitor-style bus transcript |

### Filter by file or name

```bash
pytest tests/test_protocol.py
pytest tests/test_yaml_config.py
pytest tests/test_adversarial.py

pytest -k status
pytest -k sfeer
pytest -k yaml
```

### Single test

```bash
pytest tests/test_protocol.py::test_status_reply_set_reset -v
```

## What is covered

| File | Focus |
|------|--------|
| `tests/test_protocol.py` | Encode/decode, Status replies, delays, drop Status, Program skip, Sfeer exclusivity, multi-subscriber |
| `tests/test_adversarial.py` | Rapid Status, interleaved unsolicited traffic, scripted bursts; **Program decoys** (payload that looks like a Status Set/Reset must still be skipped); **Program payload timeout** (deadline expiry resumes delivery — uses a short monkeypatched timeout, not the full production 10s); **Select/Value** light-sensor noise mid-Status |
| `tests/test_yaml_config.py` | YAML import parse/validation (`examples/demo_site.yaml`, `template.yaml`, edge fixtures) |
| `tests/test_rtc.py` | RTC Program packing (legacy byte identity), schedule phase, FakeGateway send of 9 frames |
| `tests/test_measure.py` | LDM/TSM codecs + sticky pairing (Value+System, TSM burst) |
| `tests/test_ldm_gateway.py` | LDM request TX (Data 0.2 + Select); Status drop / non-response |
| `tests/fake_gateway.py` | Adversarial TCP fake BL-NWM |
| `tests/fixtures/` | YAML edge-case fixtures |
| `b_logicx/bus_format.py` | Shared line format with blxmonitor |
| `b_logicx/rtc.py` | RTC hex4 packing + `next_phased_sync` |

### RTC bus log example

```bash
pytest tests/test_rtc.py::test_rtc_sync_send_over_fake_gateway --bus-log -s
```

Expected style (time 14:35:42 on RTC 1.1):

```text
[SENT] Program 1.1
[SENT] Set 5.66        # packing of min/sec — not a real switch
[SENT] Null 0.3        # select register 3
...
```

## Not covered (yet)

- Full Home Assistant entity lifecycle / config flow UI
- Real gateway hardware
- Cover travel-time state machine at HA entity level

Add scenarios under `tests/` as bugs appear; prefer FakeGateway knobs
(delay, drop Status, scripted `emit` / `emit_sequence`) over real bus flakiness.

## Layout reminder

```text
homeassistant_b-logicx/          # GitHub / HACS repo root
  hacs.json
  custom_components/b_logicx/    # HA integration (what HACS installs)
    b_logicx/                    # pure asyncio library
  tests/
  pytest.ini
  requirements-dev.txt
  TESTS.md
  RELEASING.md
```

Config is in `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`,
`pythonpath = custom_components/b_logicx`).
