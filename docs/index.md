---
layout: default
lang: nl
title: B-Logicx voor Home Assistant
head_title: B-Logicx voor Home Assistant, zonder Home Server
description: Koppel Home Assistant rechtstreeks aan een B-Logicx NWM of NWX. Schakelaars, dimmers, rolluiken en Sfeer, zonder B-Logicx Home Server.
last_modified_at: 2026-11-14
alternate: /en.html
---

# B-Logicx voor Home Assistant

Custom integration die [Home Assistant](https://www.home-assistant.io/) rechtstreeks koppelt aan een **[B-Logicx](https://b-logicx.be/) [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf) / NWX** bus-gateway — [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) Home Server is optioneel en geen vereiste.

## Over dit project

[B-Logicx](https://b-logicx.be/) is een Belgische producent van domotica (Heist-op-den-Berg). Hun bus gebruikt EIB/KNX-bekabeling en 24 V DC (zwart = 0, rood = +24 V, geel = bussignaal). Het systeem is van nature gedecentraliseerd en laat eenvoudig toe om de bouwstenen (input en output) te verdelen over een gebouw. Een belangrijk voordeel van B-Logicx is dat alles gevoed wordt langs de bus en dat je (binnen bepaalde grenzen) met een enkele 24 V voeding kan werken. Het protocol zelf is eenvoudig: elk datagram is **twee bytes** (commando + groep, adres).

Het probleem dat ik de laatste jaren meer en meer tegenkwam, is dat er modernere (meestal draadloze) domotica-oplossingen op de markt komen die door hun eenvoud in installatie de klassieke domotica zoals B-Logicx of Niko Home Control ouderwets laten aanvoelen. Draadloze oplossingen zijn van nature gemakkelijker in nabouw aan te brengen dan bedrade systemen, weliswaar met het nadeel dat ze meestal batterijgevoed zijn.

Dit project laat toe om bestaande systemen 'hybride' te maken. Door B-Logicx te laten praten met Home Assistant, laat het gebruikers toe om bijvoorbeeld Zigbee, Z-Wave of Shelly te gebruiken op die plaatsen waar dat de installatie enorm vereenvoudigt, zonder dat dat een tweede, parallelle systeem moet vormen naast hun bestaande B-Logicx.

De officiële methode van B-Logicx om te verbinden met Home Assistant is te beperkt en vereist bovendien een B-Logicx Home Server.

Deze integratie werkt enkel op basis van een netwerkmodule die elk systeem toch al bevat en biedt een naadloze communicatie tussen B-Logicx en Home Assistant.

## Links

- [**B-Logicx**](https://b-logicx.be/) — website van de fabrikant
- [**GitHub-repository**](https://github.com/rafverbiest/homeassistant_b-logicx)
- [**Releases**](https://github.com/rafverbiest/homeassistant_b-logicx/releases)
- [**Installeren via HACS**](https://github.com/rafverbiest/homeassistant_b-logicx#installeren-met-hacs-custom-repository)

## Functies

- Schakelaars (**[RLM](https://b-logicx.be/DataSheet/DS_RLM.pdf)** / **SoftM**), **dimmers** en **alleen-lezen** (generiek Set/Reset) adressen  
- **[Rolluiken](https://b-logicx.be/DataSheet/DS_Rolluik.pdf)** (dubbele RLM) en **Sfeer**-selectie  
- **AUD**-mediaspelers (bronnen, volume omhoog/omlaag, dempen). [BHS](https://b-logicx.be/DataSheet/DS_BHS.pdf) kan de fysieke speler bedienen; dat is getest met een [NuVoP](https://b-logicx.be/Manual/BLConfig/HTML/NuVoP.html). NUV, AUD, ASD en ART24 gebruiken dezelfde busvorm. De volledige controle kan ook langs Home Assistant; dat is getest met Spotify en hoort te werken met elke speler die Home Assistant kan koppelen. Een gekende bron, afspelen, stoppen of dempen wordt teruggeschreven zodat de [DSM](https://b-logicx.be/DataSheet/DS_DSM.pdf) schermen volgen.  
- **SoftM** virtuele statusmodule (VSM) in Home Assistant  
- **TCP bus repeater** — deel de ene [NWM](https://b-logicx.be/DataSheet/DS_NWM.pdf)-verbinding met [BLConfig](https://b-logicx.be/Manual/BLConfig/HTML/Introductie.html) / blxmonitor  
- **[RTC](https://b-logicx.be/DataSheet/DS_RTC.pdf)**-synchronisatie (incl. DST), **[LDM](https://b-logicx.be/DataSheet/DS_LDM.pdf)**-lichtsensor, **[TSM](https://b-logicx.be/DataSheet/DS_TSM.pdf)**-thermostaat, **[WSM](https://b-logicx.be/DataSheet/DS_WSM.pdf)**-windsnelheid (km/h), **[BM8](https://b-logicx.be/DataSheet/DS_BM8.pdf)**-deurbel  
- YAML import/export van adressen  

<img src="/images/integration.png" alt="Integratiepagina met de apparaten onder de gateway." width="1128" height="811">

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
