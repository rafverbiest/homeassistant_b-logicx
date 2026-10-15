---
layout: default
lang: en
title: "Installation"
description: "Install with HACS or by hand, then add the gateway."
last_modified_at: 2026-10-15
alternate: /Installatie.html
permalink: /Installation.html
---

# Installation

[Nederlands](/Installatie.html) · **English** · [← Home](/en.html)

## Via HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if needed.
2. In Home Assistant: **HACS** → top-right **⋮** → **Custom repositories**.
3. Repository URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Category: **Integration**
4. **Add** → find **B-Logicx** → **Download**.
5. **Restart** Home Assistant.
6. **Settings → Devices & services → Add integration → B-Logicx**.
7. Enter the **IP address** of the NWM / NWX (default port `10001`).

Also see the [README](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository).

## Manual (without HACS)

1. Copy the `custom_components/b_logicx` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration as above (steps 6–7).

## First configuration

After adding the integration:

- Configure **addresses** in the options UI (add / edit / remove), or  
- Import a YAML file ([YAML](/YAML-en.html), template: `custom_components/b_logicx/flow/template.yaml`).

Optional later: SoftM status tracking and the TCP bus repeater under **integration settings** — see [SoftM](/SoftM-en.html) and [Bus repeater](/Bus-repeater-en.html).
