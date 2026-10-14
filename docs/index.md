---
layout: default
lang: nl
title: B-Logicx voor Home Assistant
last_modified_at: 2026-10-14
---

# B-Logicx voor Home Assistant

**Nederlands** · [English](en.html)

Custom integration die Home Assistant rechtstreeks koppelt aan een **[B-Logicx](https://b-logicx.be/) [BL-NWM / BL-NWX](https://b-logicx.be/Manual/BLConfig/HTML/Netwerkverbinding.html)** bus-gateway — [BL-BHS](https://b-logicx.be/Manual/BLConfig/HTML/BHS.html) Home Server is optioneel en geen vereiste.

## Links

- [**B-Logicx**](https://b-logicx.be/) — website van de fabrikant
- [**GitHub-repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Wiki (documentatie)**](https://github.com/rafverbiest/homeassistant_b-logicx/wiki)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Installeren via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx#installeren-met-hacs-custom-repository)

## Functies

- Schakelaars ([RLM](https://b-logicx.be/Manual/BLConfig/HTML/RLM.html) / [SoftM](https://b-logicx.be/Manual/BLConfig/HTML/STM.html)), **[dimmers](https://b-logicx.be/Manual/BLConfig/HTML/DIM1K.html)** en **alleen-lezen** adressen  
- **[Rolluiken](https://b-logicx.be/Manual/BLConfig/HTML/ReeksRolluiken.html)** (dubbele RLM) en **[Sfeer](https://b-logicx.be/Manual/BLConfig/HTML/Sferen.html)**-selectie  
- **[BL-AUD](https://b-logicx.be/Manual/BLConfig/HTML/AUD.html)** als mediaspeler (bronnen, volume omhoog/omlaag, dempen). [BHS](https://b-logicx.be/Manual/BLConfig/HTML/BHS.html) kan de fysieke speler bedienen, of de volledige controle kan langs Home Assistant. Een gekende bron, afspelen, stoppen of dempen van die speler wordt teruggeschreven zodat de [DSM](https://b-logicx.be/Manual/BLConfig/HTML/DSM.html) schermen volgen.  
- **[SoftM](https://b-logicx.be/Manual/BLConfig/HTML/STM.html)** virtuele statusmodule (VSM) in Home Assistant  
- **TCP bus repeater** — deel de ene [NWM](https://b-logicx.be/Manual/BLConfig/HTML/Netwerkverbinding.html)-verbinding met [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/Manual/BLConfig/HTML/RTC.html)**-synchronisatie (incl. DST), **[LDM](https://b-logicx.be/Manual/BLConfig/HTML/LDM.html)**-lichtsensor, **[TSM](https://b-logicx.be/Manual/BLConfig/HTML/TSM.html)**-thermostaat, **[WSM](https://b-logicx.be/Manual/BLConfig/HTML/WSM.html)**-windsnelheid (km/h), **[BL-BM8](https://b-logicx.be/Manual/BLConfig/HTML/BM8.html)**-deurbel  
- YAML import/export van adressen  

## Documentatie

Meer uitleg staat in de [wiki](https://github.com/rafverbiest/homeassistant_b-logicx/wiki):

[Installatie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installatie) ·
[Configuratie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuratie) ·
[Dimmer](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Dimmer) ·
[SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM) ·
[Bus-repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater) ·
[Diagnostiek](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostiek) ·
[YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML) ·
[B-Logicx upgrades](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Alternatieven)

## Belangrijk

Deze integratie is onafhankelijk geproduceerd. Ik ben zelf **niet** gelieerd aan [B-Logicx](https://b-logicx.be/).  
**[BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html)** blijft nodig om hardware te programmeren; deze HA-integratie bestuurt en monitort de bus nadat die geconfigureerd is.

## Licentie

Zie [LICENSE](https://github.com/rafverbiest/homeassistant_b-logicx/blob/main/LICENSE) in de repository.

## Auteur

Ik heb dit ontwikkeld, oorspronkelijk voor eigen gebruik, en om te vermijden dat B-Logicx verouderd zou raken door de opkomst van modernere en performantere systemen.

In mijn visie is Home Assistant de motor van *The Internet of Things*; dingen die er niet (goed) mee integreren zullen op termijn verdwijnen.

Zelf beheer ik een heleboel gebouwen waar B-Logicx geïmplementeerd is; voor mij is dit de manier om ervoor te zorgen dat deze gebouwen niet binnenkort moeten worden uitgerust met andere domoticasystemen.

De code plaatste ik dus online in de poging B-Logicx 'future-proof' te maken, maar ook om in contact te komen met andere B-Logicx-gebruikers. Hoe wijdverspreid is dit systeem? Laat het me weten!

Als dit project je helpt (of je krijgt iets niet in orde), stuur me gerust een mailtje: raf.verbiest@gmail.com
