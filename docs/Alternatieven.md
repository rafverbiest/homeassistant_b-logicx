---
layout: default
lang: nl
title: "B-Logicx upgrades"
description: "Wat Home Assistant overneemt van oudere B-Logicx-modules."
last_modified_at: 2026-10-15
alternate: /Alternatives.html
permalink: /Alternatieven.html
---

# B-Logicx upgrades

**Nederlands** · [English](/Alternatives.html) · [← Home](/)

## Sommige modules zijn niet meer nodig

Met een **NWM / NWX** en deze Home Assistant-integratie zit HA al op de B-Logicx-bus. Daardoor is een apart B-Logicx-WiFi-traject voor schakelaars niet meer nodig.

**ST2**, **ST4** en **WRL** bieden een manier om B-Logicx te koppelen aan een (dedicated) WiFi-netwerk en zo schakelaars of acties op afstand te bedienen.

Omdat deze integratie de bus rechtstreeks monitort en bestuurt, kun je voor *nieuwe* draadloze schakelaars en actuatoren vaak kiezen voor wat Home Assistant al goed ondersteunt — bijvoorbeeld **Shelly**, **Zigbee**, **Matter**, of een andere HA-integratie — en die in HA laten samenwerken met je bestaande B-Logicx-leden (RLM’s, SoftM’s, sfeer, RTC, …).

Je bouwt dan geen tweede, parallel bedieningsnetwerk naast de bus; HA is de gemeenschappelijke laag.

- **Voorbeeld:** gebruik een Niko-schakelaar met een INM om een Shelly of Zigbee-stopcontact te schakelen (spotgoedkoop op Amazon of bij IKEA te verkrijgen)

## Automatisaties

### RLM

B-Logicx voorziet in één AND- en één OR-poort per RLM, alsook een stappenautomaat.

### INM

In elke INM zit een ‘Virtuele sturing’ en een ‘Software Member Timer’.

### Deze integratie

Door gebruik te maken van Home Assistant zijn allerlei complexere automatisaties mogelijk, zonder limieten, over de grenzen van de verschillende technologieën heen. Bijvoorbeeld:

- Met Zigbee-raam/deursensoren: laat niet toe dat het rolgordijn zich sluit als het raam nog open staat, om schade te voorkomen.
- Lees het tarief uit van je digitale meter (of online als je prijs per kwartier bepaald wordt) en schakel niet-prioritaire gebruikers via RLM’s in en uit afhankelijk van drempelwaarden.
- Zet je boiler aan of uit met een RLM, gebaseerd op de opbrengst van je zonnepanelen. Lees dit rechtstreeks uit de omvormer, en hou zelfs rekening met het weerbericht.
