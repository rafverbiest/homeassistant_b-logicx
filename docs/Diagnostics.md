---
layout: default
lang: en
title: "Diagnostics (blxmonitor)"
description: "Watch the bus with blxmonitor."
last_modified_at: 2026-10-15
alternate: /Diagnostiek.html
permalink: /Diagnostics.html
---

# Diagnostics (blxmonitor)

[Nederlands](/Diagnostiek.html) · **English** · [← Home](/en.html)

`blxmonitor.py` is a command-line bus monitor/sender. It lives in the library package (not next to HA platforms like `select.py`, which would shadow the stdlib `select` module):

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-or-gateway-ip> -p 10001
```

## Options

| Option | Meaning |
|--------|---------|
| `-i` / `--ip-address` | Gateway IP, or HA IP when the [bus repeater](/Bus-repeater-en.html) is on |
| `-p` / `--port` | Port (default `10001`) |
| `--hide-program` | Hide Program + the two following payload frames |
| `-l` / `--log-file PATH` | Append every TX/RX line (with date+time) to a file |

Example with a log file (handy under `screen`/`tmux`):

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py \
  -i 127.0.0.1 -p 10001 -l /config/blxbus.log
```
