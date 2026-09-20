---
layout: default
title: B-Logicx for Home Assistant
---

# B-Logicx for Home Assistant

[Nederlands](index.html) · **English**

Custom integration that connects Home Assistant directly to a **B-Logicx BL-NWM / BL-NWX** bus gateway — no BHS Home Server required.

## Links

- [**GitHub repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Wiki (documentation)**](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Install via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository)

## Features

- Switches (RLM / SoftM) and **read-only** addresses  
- **Covers** (dual RLM) and **Sfeer** selection  
- **SoftM** virtual status module (VSM) inside Home Assistant  
- **TCP bus repeater** — share the single NWM link with BLConfig / blxmonitor  
- **RTC** sync (incl. DST), **LDM** light sensor, **TSM** thermostat  
- YAML import/export of addresses  

## Documentation

Deeper guides live in the [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en):

[Installation](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installation) ·
[Configuration](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuration) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM-en) ·
[Bus repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater-en) ·
[Diagnostics](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostics) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML-en)

## Important

This integration is **not** affiliated with [B-Logicx](https://b-logicx.be/).  
**BLConfig** remains required to program hardware; this project monitors and controls the bus after it is configured.

## License

See [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in the repository.
