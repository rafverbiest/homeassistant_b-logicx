---
layout: default
lang: nl
title: B-Logicx voor Home Assistant
head_title: B-Logicx voor Home Assistant, zonder de Home Server
description: Koppel Home Assistant rechtstreeks aan een B-Logicx NWM of NWX. Schakelaars, dimmers, rolluiken en Sfeer, zonder B-Logicx Home Server.
last_modified_at: 2026-11-21
alternate: /en.html
---

# B-Logicx voor Home Assistant

Custom integration die [Home Assistant](https://www.home-assistant.io/) rechtstreeks koppelt aan een **[B-Logicx](https://b-logicx.be/) [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) / NWX** bus-gateway — [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) Home Server is optioneel en geen vereiste.

## Functies

- Schakelaars (**[RLM](https://b-logicx.be/DataSheet/DS_RLM.pdf)** / **SoftM**), **dimmers** en **alleen-lezen** (generiek Set/Reset) adressen  
- **[Rolluiken](https://b-logicx.be/DataSheet/DS_Rolluik.pdf)** (dubbele RLM) en **Sfeer**-selectie  
- **SoftM** virtuele statusmodule (VSM) in Home Assistant  
- **TCP bus repeater** — deel de ene [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf)-verbinding met [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/DataSheet/DS_RTC.pdf)**-synchronisatie (incl. DST), **[LDM](https://b-logicx.be/DataSheet/DS_LDM.pdf)**-lichtsensor, **[TSM](https://b-logicx.be/DataSheet/DS_TSM.pdf)**-thermostaat, **[WSM](https://b-logicx.be/DataSheet/DS_WSM.pdf)**-windsnelheid (km/h), **[BM8](https://b-logicx.be/DataSheet/DS_BM8.pdf)**-deurbel  
- **AUD**-mediaspelers: bronnen, volume en dempen. Getest met een NuVoP via BHS, en met Spotify via Home Assistant.  
- **Importeren** van adressen: YAML (import en export), of eenmalig de ledenlijst van BHS of het databasebestand van BLConfig (FDB). BHS en FDB zijn experimenteel; je vinkt aan wat je toevoegt. Het FDB-bestand wordt gelezen en niet bewaard.  

<img src="/images/integration.png" alt="Integratiepagina met de apparaten onder de gateway." width="1128" height="811">

## Over dit project

[B-Logicx](https://b-logicx.be/) is een Belgische producent van domotica (Heist-op-den-Berg). Hun bus gebruikt EIB/KNX-bekabeling en 24 V DC (zwart = 0, rood = +24 V, geel = bussignaal). Het systeem is van nature gedecentraliseerd en laat eenvoudig toe om de bouwstenen (input en output) te verdelen over een gebouw. Een belangrijk voordeel van B-Logicx is dat alles gevoed wordt langs de bus en dat je (binnen bepaalde grenzen) met een enkele 24 V voeding kan werken. Het protocol zelf is eenvoudig: elk datagram is **twee bytes** (commando + groep, adres).

### Na-installatie

Het probleem dat ik de laatste jaren meer en meer ondervond, is dat er modernere (meestal draadloze) domotica-oplossingen op de markt komen die door hun eenvoudige installatie de klassieke domotica zoals B-Logicx of Niko Home Control ouderwets laten aanvoelen. Draadloze oplossingen hebben wel het nadeel dat ze vaak batterijgevoed zijn, maar ze zijn wel veel makkelijker en vaak zonder veel ervaring aan te brengen, wat ze vooral voor na-installaties aantrekkelijk maakt.

### Hybride

Dit project zorgt ervoor dat je niet hoeft te kiezen: het laat toe om bestaande systemen **hybride** te maken. Door B-Logicx te laten praten met Home Assistant, laat het toe om bijvoorbeeld Zigbee, Z-Wave of Shelly te installeren op die plaatsen waar dat de installatie enorm vereenvoudigt, zonder dat dat een tweede, parallelle systeem moet vormen naast de bestaande B-Logicx.

De officiële methode van B-Logicx om te verbinden met Home Assistant is te beperkt en vereist bovendien een B-Logicx Home Server.

Deze integratie werkt **enkel op basis van een netwerkmodule** die elk systeem toch al bevat en biedt een naadloze en real-time communicatie tussen B-Logicx en Home Assistant.

## Links

- [**B-Logicx**](https://b-logicx.be/) — website van de fabrikant
- [**GitHub-repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Installeren via HACS**](/Installatie.html)

## Documentatie

[Installatie](/Installatie.html) ·
[Configuratie](/Configuratie.html) ·
[Dimmer](/Dimmer.html) ·
[SoftM](/SoftM.html) ·
[Bus-repeater](/Bus-repeater.html) ·
[Diagnostiek](/Diagnostiek.html) ·
[YAML](/YAML.html) ·
[B-Logicx upgrades](/Alternatieven.html)

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
