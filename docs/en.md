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

More detail lives in the [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en):

[Installation](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installation) ·
[Configuration](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuration) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM-en) ·
[Bus repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater-en) ·
[Diagnostics](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostics) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML-en) ·
[B-Logicx upgrades](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Alternatives)

## Important

This integration was produced independently. I am **not** affiliated with [B-Logicx](https://b-logicx.be/).  
**BLConfig** remains required to program hardware; this HA integration monitors and controls the bus after it is configured.

## License

See [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in the repository.

## Author

I built this originally for my own use, and to help keep B-Logicx from becoming obsolete as newer systems appear.

In my view Home Assistant is the engine of *The Internet of Things*; things that do not integrate with it (well) will disappear over time.

I manage a large number of buildings where B-Logicx is installed; for me this is how those buildings avoid having to be refitted with other home-automation systems anytime soon.

I put the code online to help make B-Logicx more future-proof, and to get in touch with other B-Logicx users. How widespread is this system? Let me know!

If this project helps you (or something is not working), feel free to email me: raf.verbiest@gmail.com
