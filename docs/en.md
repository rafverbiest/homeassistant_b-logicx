---
layout: default
lang: en
title: B-Logicx for Home Assistant
head_title: B-Logicx for Home Assistant, without a Home Server
description: Connect Home Assistant directly to a B-Logicx NWM or NWX. Switches, dimmers, covers and Sfeer, with no B-Logicx Home Server required.
last_modified_at: 2026-11-14
alternate: /
---

# B-Logicx for Home Assistant

Custom integration that connects [Home Assistant](https://www.home-assistant.io/) directly to a **[B-Logicx](https://b-logicx.be/) [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) / NWX** bus gateway — the [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) Home Server is optional and not a requirement.

## About this project

[B-Logicx](https://b-logicx.be/) is a Belgian home-automation vendor (Heist-op-den-Berg). Their bus uses EIB/KNX cabling and 24 V DC (black = 0, red = +24 V, yellow = bus signal). The system is decentralised by nature and makes it easy to spread the building blocks (inputs and outputs) through a building. An important advantage of B-Logicx is that everything is powered over the bus, and that (within certain limits) a single 24 V supply is enough. The protocol is simple: each datagram is **two bytes** (command + group, address).

The problem I ran into more and more over recent years is that newer, usually wireless, home-automation products make classic systems such as B-Logicx or Niko Home Control feel dated, because they are simple to install. Wireless products are by nature easier to add during later building work than wired systems, with the drawback that they usually run on batteries.

This project lets an existing system become a hybrid. By letting B-Logicx talk to Home Assistant, people can use Zigbee, Z-Wave or Shelly where that makes the installation much simpler, without that becoming a second, parallel system beside their existing B-Logicx.

The official B-Logicx way to connect to Home Assistant is too limited, and it also requires a B-Logicx Home Server.

This integration needs only the network module every system already has, and it provides seamless communication between B-Logicx and Home Assistant.

## Links

- [**B-Logicx**](https://b-logicx.be/) — the manufacturer's website
- [**GitHub repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Install via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/README.en.md#install-with-hacs-custom-repository)

## Features

- Switches (**[RLM](https://b-logicx.be/DataSheet/DS_RLM.pdf)** / **SoftM**), **dimmers**, and **read-only** addresses (generic Set/Reset)  
- **[Covers](https://b-logicx.be/DataSheet/DS_Rolluik.pdf)** (dual RLM) and **Sfeer** selection  
- **AUD** media players (sources, volume up/down, mute). [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) can control the physical player; that was tested with a [NuVoP](https://b-logicx.be/Manual/BLConfig/HTML/NuVoP.html). NUV, AUD, ASD, and ART24 use the same bus shape. Full control can also go through Home Assistant; that was tested with Spotify and should work with any player Home Assistant can link. A known source, play, stop, or mute is written back so the [DSM](https://b-logicx.be/DataSheet/DS_DSM.pdf) displays follow.  
- **SoftM** virtual status module (VSM) inside Home Assistant  
- **TCP bus repeater** — share the single [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) link with [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/DataSheet/DS_RTC.pdf)** sync (incl. DST), **[LDM](https://b-logicx.be/DataSheet/DS_LDM.pdf)** light sensor, **[TSM](https://b-logicx.be/DataSheet/DS_TSM.pdf)** thermostat, **[WSM](https://b-logicx.be/DataSheet/DS_WSM.pdf)** wind speed (km/h), **[BM8](https://b-logicx.be/DataSheet/DS_BM8.pdf)** doorbell  
- YAML import/export of addresses  

<img src="/images/integration.png" alt="Integration page with the devices under the gateway." width="1128" height="811">

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
