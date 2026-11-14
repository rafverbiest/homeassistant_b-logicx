---
layout: default
lang: en
title: "Installation"
description: "Install with HACS or by hand, then add the gateway."
last_modified_at: 2026-10-20
alternate: /Installatie.html
permalink: /Installation.html
---

# Installation

## Via HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if you do not already have it (no longer needed from Home Assistant 2026.11 on).
2. In Home Assistant: **HACS** (**marketplace** in >2026.11) → top-right **⋮** → **Custom repositories**.
3. Repository URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Category: **Integration**
4. **Add** → find **B-Logicx** → **Download**.
5. **Restart** Home Assistant.
6. **Settings → Devices & services → Add integration → B-Logicx**.
7. Enter the **IP address** of the NWM / NWX (default port `10001`).

When a gateway answers, pick it. Otherwise type the address.

![Found gateway, or enter an address yourself.](/images/discover-gateway.png)

Also see the [README](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository).

## Manual (without HACS)

1. Copy the `custom_components/b_logicx` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration as above (steps 6–7).

## First configuration

After adding the integration:

- Configure **addresses** in the options UI (add / edit / remove), or  
- Import a YAML file ([YAML](/YAML-en.html), template: `custom_components/b_logicx/flow/template.yaml`).
- New feature: automatic detection of the bus gateway and the bus addresses.

Optional later: turn on the Virtual Status Module and the TCP bus repeater in **integration settings** — see [SoftM](/SoftM-en.html) and [Bus repeater](/Bus-repeater-en.html).
