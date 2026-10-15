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

[Nederlands](/Bus-repeater.html) · **English** · [← Home](/en.html)

NWM / NWX accept **one** TCP client. With the repeater enabled, Home Assistant keeps that single link and listens on HA (default port `10001`) so **BLConfig** / **blxmonitor** on the same LAN subnet as the NWM can share the bus.

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

## Warning

The repeater is still lightly tested. Do **not** rely on it yet as the only path for critical **Program** actions by BLConfig.
