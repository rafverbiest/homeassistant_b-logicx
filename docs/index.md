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

Meer uitleg staat in de [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki):

[Installatie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installatie) ·
[Configuratie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuratie) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM) ·
[Bus-repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater) ·
[Diagnostiek](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostiek) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML) ·
[B-Logicx upgrades](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Alternatieven)

## Belangrijk

Deze integratie is onafhankelijk geproduceerd. Ik ben zelf **niet** gelieerd aan [B-Logicx](https://b-logicx.be/).  
**BLConfig** blijft nodig om hardware te programmeren; deze HA-integratie bestuurt en monitort de bus nadat die geconfigureerd is.

## Licentie

Zie [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in de repository.

## Auteur

Ik heb dit ontwikkeld, oorspronkelijk voor eigen gebruik, en om te vermijden dat B-Logicx verouderd zou raken door de opkomst van modernere systemen.

In mijn visie is Home Assistant de motor van *The Internet of Things*; dingen die er niet (goed) mee integreren zullen op termijn verdwijnen.

Zelf beheer ik een heleboel gebouwen waar B-Logicx geïmplementeerd is; voor mij is dit de manier om ervoor te zorgen dat deze gebouwen niet binnenkort moeten worden uitgerust met andere domoticasystemen.

De code plaatste ik dus online in de poging B-Logicx 'future-proof' te maken, maar ook om in contact te komen met andere B-Logicx-gebruikers. Hoe wijdverspreid is dit systeem? Laat het me weten!

Als dit project je helpt (of je krijgt iets niet in orde), stuur me gerust een mailtje: raf.verbiest@gmail.com
