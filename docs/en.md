---
layout: default
lang: en
title: B-Logicx for Home Assistant
description: Home Assistant integration for the B-Logicx bus gateway (NWM / NWX)
last_modified_at: 2026-10-15
alternate: /
---

# B-Logicx for Home Assistant

[Nederlands](index.html) · **English**

Custom integration that connects [Home Assistant](https://www.home-assistant.io/) directly to a **[B-Logicx](https://b-logicx.be/) [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) / NWX** bus gateway — the [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) Home Server is optional and not a requirement.

## About this project

[B-Logicx](https://b-logicx.be/) is a Belgian home-automation vendor (Heist-op-den-Berg). Their bus uses EIB/KNX cabling and 24 V DC (black = 0, red = +24 V, yellow = bus signal). The protocol is simple: each datagram is **two bytes** (command + group, address).

## Links

- [**B-Logicx**](https://b-logicx.be/) — the manufacturer's website
- [**GitHub repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Install via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository)

## Features

- Switches ([RLM](https://b-logicx.be/DataSheet/DS_RLM.pdf) / SoftM), **dimmers**, and **read-only** addresses  
- **[Covers](https://b-logicx.be/DataSheet/DS_Rolluik.pdf)** (dual RLM) and **Sfeer** selection  
- **AUD** media players (sources, volume up/down, mute). [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) can control the physical player; that was tested with a [NuVoP](https://b-logicx.be/Manual/BLConfig/HTML/NuVoP.html). NUV, AUD, ASD, and ART24 use the same bus shape. Full control can also go through Home Assistant; that was tested with Spotify and should work with any player Home Assistant can link. A known source, play, stop, or mute is written back so the [DSM](https://b-logicx.be/DataSheet/DS_DSM.pdf) displays follow.  
- **SoftM** virtual status module (VSM) inside Home Assistant  
- **TCP bus repeater** — share the single [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) link with [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/DataSheet/DS_RTC.pdf)** sync (incl. DST), **[LDM](https://b-logicx.be/DataSheet/DS_LDM.pdf)** light sensor, **[TSM](https://b-logicx.be/DataSheet/DS_TSM.pdf)** thermostat, **[WSM](https://b-logicx.be/DataSheet/DS_WSM.pdf)** wind speed (km/h), **[BM8](https://b-logicx.be/DataSheet/DS_BM8.pdf)** doorbell  
- YAML import/export of addresses  

<div class="ha-cards">
<img src="/images/card-dimmer-en.png" alt="More-info for Table lamp: brightness 70 percent, with the vertical bar and power button">
<img src="/images/card-cover-en.png" alt="More-info for Roller shutter: open, with up, stop, and down buttons stacked">
<img src="/images/card-sfeer-en.png" alt="More-info for Sfeer: menu set to Evening">
<img src="/images/card-aud-en.png" alt="More-info for AUD: Spotify is playing, with a pause button and volume bar">
</div>

## Documentation

[Installation](/Installation.html) ·
[Configuration](/Configuration.html) ·
[Dimmer](/Dimmer-en.html) ·
[SoftM](/SoftM-en.html) ·
[Bus repeater](/Bus-repeater-en.html) ·
[Diagnostics](/Diagnostics.html) ·
[YAML](/YAML-en.html) ·
[B-Logicx upgrades](/Alternatives.html)

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
