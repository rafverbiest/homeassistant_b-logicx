---
layout: default
lang: en
title: B-Logicx for Home Assistant
description: Home Assistant integration for the B-Logicx bus gateway (NWM / NWX)
last_modified_at: 2026-10-14
---

# B-Logicx for Home Assistant

[Nederlands](index.html) · **English**

Custom integration that connects Home Assistant directly to a **[B-Logicx](https://b-logicx.be/) [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) / NWX** bus gateway — the [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) Home Server is optional and not a requirement.

## Links

- [**B-Logicx**](https://b-logicx.be/) — the manufacturer's website
- [**GitHub repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Wiki (documentation)**](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Install via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository)

## Features

- Switches ([RLM](https://b-logicx.be/DataSheet/DS_RLM.pdf) / SoftM), **dimmers**, and **read-only** addresses  
- **[Covers](https://b-logicx.be/DataSheet/DS_Rolluik.pdf)** (dual RLM) and **Sfeer** selection  
- **AUD** as a media player (sources, volume up/down, mute). [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) can control the physical player, or full control can go through Home Assistant. A known source, play, stop, or mute on that player is written back so the [DSM](https://b-logicx.be/DataSheet/DS_DSM.pdf) displays follow.  
- **SoftM** virtual status module (VSM) inside Home Assistant  
- **TCP bus repeater** — share the single [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) link with [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/DataSheet/DS_RTC.pdf)** sync (incl. DST), **[LDM](https://b-logicx.be/DataSheet/DS_LDM.pdf)** light sensor, **[TSM](https://b-logicx.be/DataSheet/DS_TSM.pdf)** thermostat, **[WSM](https://b-logicx.be/DataSheet/DS_WSM.pdf)** wind speed (km/h), **[BM8](https://b-logicx.be/DataSheet/DS_BM8.pdf)** doorbell  
- YAML import/export of addresses  

## Documentation

More detail lives in the [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Home-en):

[Installation](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installation) ·
[Configuration](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuration) ·
[Dimmer](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Dimmer-en) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM-en) ·
[Bus repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater-en) ·
[Diagnostics](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostics) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML-en) ·
[B-Logicx upgrades](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Alternatives)

## Important

This integration was produced independently. I am **not** affiliated with [B-Logicx](https://b-logicx.be/).  
**[BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html)** remains required to program hardware; this HA integration monitors and controls the bus after it is configured.

## License

See [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in the repository.

## Author

I built this originally for my own use, and to help keep B-Logicx from becoming obsolete as newer systems appear.

In my view Home Assistant is the engine of *The Internet of Things*; things that do not integrate with it (well) will disappear over time.

I manage a large number of buildings where B-Logicx is installed; for me this is how those buildings avoid having to be refitted with other home-automation systems anytime soon.

I put the code online to help make B-Logicx more future-proof, and to get in touch with other B-Logicx users. How widespread is this system? Let me know!

If this project helps you (or something is not working), feel free to email me: raf.verbiest@gmail.com
