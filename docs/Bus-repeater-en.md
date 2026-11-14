---
layout: default
lang: en
title: "TCP bus repeater"
description: "Share the one NWM connection with BLConfig."
last_modified_at: 2026-10-15
alternate: /Bus-repeater.html
permalink: /Bus-repeater-en.html
---

# TCP bus repeater

B-Logicx bus gateways (NWM / NWX) accept only **one** TCP client. With the repeater, Home Assistant keeps that single link open and listens on HA (default port `10001`). The BHS (B-Logicx Home Server), for example, can stay connected to the bus at the same time by pointing its connection at the Home Assistant IP address.
BLConfig can be used the same way without switching Home Assistant off.

The BHS has a similar feature, so if you have a BHS you can still choose which of the two (BHS or Home Assistant) sits in front.

## Enabling

1. **Integration settings** → *Enable TCP bus repeater* (port default `10001`).
2. Point BLConfig / blxmonitor at the **Home Assistant IP**, not the gateway IP.  
   On the HA host itself you may use `127.0.0.1` (localhost is always allowed).

## Access

In integration settings you enter a **CIDR** (for example `192.168.50.0/24`). Only clients in that subnet are allowed.

- **Localhost** (loopback): always allowed.  
- Empty subnet: previous behaviour (the gateway address’s `/24`).

## Without the repeater

Without this feature you need a second NWM/NWX or a **NWM2** to run HA and BLConfig at the same time.
