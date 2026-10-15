---
layout: default
lang: nl
title: "Diagnostiek (blxmonitor)"
description: "De bus volgen met blxmonitor."
last_modified_at: 2026-10-15
alternate: /Diagnostics.html
permalink: /Diagnostiek.html
---

# Diagnostiek (blxmonitor)

**Nederlands** · [English](/Diagnostics.html) · [← Home](/)

`blxmonitor.py` is een command-line busmonitor/zender. Het leeft in het library-pakket (niet naast HA-platforms zoals `select.py`, die anders de stdlib `select` zouden shadowen):

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-of-gateway-ip> -p 10001
```

## Opties

| Optie | Betekenis |
|-------|-----------|
| `-i` / `--ip-address` | IP van de gateway, of van HA als de [bus repeater](/Bus-repeater.html) aan staat |
| `-p` / `--port` | Poort (standaard `10001`) |
| `--hide-program` | Verberg Program + de twee volgende payload-frames |
| `-l` / `--log-file PATH` | Append elke TX/RX-regel (met datum+tijd) naar een bestand |

Voorbeeld met logfile (handig onder `screen`/`tmux`):

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py \
  -i 127.0.0.1 -p 10001 -l /config/blxbus.log
```
