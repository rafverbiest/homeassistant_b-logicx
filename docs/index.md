---
layout: default
title: B-Logicx voor Home Assistant
---

# B-Logicx voor Home Assistant

**Nederlands** · [English](en.html)

Custom integration die Home Assistant rechtstreeks koppelt aan een **B-Logicx BL-NWM / BL-NWX** bus-gateway — zonder BHS Home Server.

## Links

- [**GitHub-repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Wiki (documentatie)**](https://github.com/rafverbiest/homeassistant_b-logicx/wiki)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Installeren via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx#installeren-met-hacs-custom-repository)

## Functies

- Schakelaars (RLM / SoftM) en **alleen-lezen** adressen  
- **Rolluiken** (dubbele RLM) en **Sfeer**-selectie  
- **SoftM** virtuele statusmodule (VSM) in Home Assistant  
- **TCP bus repeater** — deel de ene NWM-verbinding met BLConfig / blxmonitor  
- **RTC**-synchronisatie (incl. DST), **LDM**-lichtsensor, **TSM**-thermostaat  
- YAML import/export van adressen  

## Documentatie

Diepere uitleg staat in de [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki):

[Installatie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installatie) ·
[Configuratie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuratie) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM) ·
[Bus-repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater) ·
[Diagnostiek](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostiek) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML)

## Belangrijk

Deze integratie is **niet** gelieerd aan [B-Logicx](https://b-logicx.be/).  
**BLConfig** blijft nodig om hardware te programmeren; dit project bestuurt en monitort de bus nadat die geconfigureerd is.

## Licentie

Zie [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in de repository.
