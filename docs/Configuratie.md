---
layout: default
lang: nl
title: "Configuratie"
description: "Adrestypes, de optieschermen, en YAML-import."
last_modified_at: 2026-10-22
alternate: /Configuration.html
permalink: /Configuratie.html
---

# Configuratie

**Nederlands** · [English](/Configuration.html) · [← Home](/)

Adressen beheer je in de **integratie-opties** (UI) of via [YAML](/YAML.html)-import/export. Het hoofdmenu toont alleen een **aantal** entries — geen volledige dump van alle leden.

![Configuratiemenu, met een tweede regel per optie.](/images/configure-menu.png)

Adres detecteren luistert hoogstens 30 seconden. Een RLM of SoftM zet je aan of uit. Een rolluik stuur je eerst omhoog en daarna omlaag. Voor het rolluik telt Set: dat is de richting die je stuurde. Reset is het andere relais.

Importeren uit BHS leest eenmalig de ledenlijst op de BHS (poort 10014) en voegt de aangevinkte modules toe.

![Adres detecteren, luisterend naar Set of Reset.](/images/detect-address.png)

## Adrestypes

| YAML | HA-entity | Opmerking |
|------|-----------|-----------|
| `rlm` | `switch` | `on_command` / `off_command` (Set, Reset, Toggle, …) |
| `dimmer` | `light` | Fysiek adres. Schuifregelaar 0–100. Aan/uit is een korte Dimmer-puls; Set/Reset is het antwoord. Zie [Dimmer](/Dimmer.html) |
| `softm` | `switch` | Zelfde commando's. Tracking en timer: [SoftM](/SoftM.html) |
| `readonly` | `binary_sensor` | Alleen Set/Reset observeren; geen sturing |
| `shutter` | `cover` | Open- en sluitpaar (dubbele RLM) |
| `sfeer` | `select` | Kamer + moods (groep/adres per sfeer) |
| `ldm` | `sensor` (+ optionele refresh-knop) | Lichtsensor |
| `tsm` | `sensor`s (+ optionele refresh) | Thermostaattelemetrie |
| `wsm` | `sensor` (+ optionele vernieuwen-knop) | Windsnelheid, km/h. Zie hieronder |
| `bm8` | `button`s | Deurbel, 8 beltonen en stop. Zie hieronder |
| `rtc` | (geen stuur-entity) | Periodieke + DST-kloksync |
| `aud` | `media_player` | Virtuele audiomodule, meestal groep 4. `controller: bhs` of `ha`. Zie hieronder |

Een adres dat je verwijdert, verdwijnt bij het herladen ook uit de apparatenlijst onder de gateway.

![Twee rolluiken op een dashboard.](/images/dashboard-cover.png)

![Een rolluik en een Sfeer-keuze op een dashboard.](/images/dashboard-sfeer.png)

## AUD

`controller` is verplicht: `bhs` of `ha`. `bhs` laat het bedienen van de fysieke speler over aan BHS. De acht `source_*`-namen zijn labels op de widget in Home Assistant. 

BHS-bediening is getest met een [NuVoP](https://b-logicx.be/Manual/BLConfig/HTML/NuVoP.html). NUV, AUD, ASD en ART24 gebruiken (volgens mij) dezelfde controle. 

Bediening door Home Assistant (`controller: ha`) is getest met Spotify maar zou moeten werken met elke mediaspeler die Home Assistant kan koppelen (zoals Sonos, enz.).
Schakel hem best aan voor je de configuratie start. Elke `source_*` is een bron die die externe speler aan HA meldt. Een DSM-schermmodule, of deze widget, stuurt nog steeds `Misc` en `Select`. Home Assistant bedient daarna afspelen, het bewaarde stopcommando, het volume, het bewaarde dempcommando of `select_source` op de gekoppelde speler.

Wordt er op die gekoppelde speler een andere bron uit de acht namen gekozen, of verandert afspelen, stoppen of dempen, dan wordt deze widget bijgewerkt en stuurt `Misc` en `Select`, zodat de DSM-schermen volgen. Een bron buiten die acht namen wordt genegeerd.

In het configuratiescherm kies je eerst BHS of Home Assistant, en daarna de bronnamen. Bij Home Assistant kies je de mediaspeler terwijl die aan staat, zodat zijn mogelijkheden gelezen worden. Het volgende scherm toont alleen de stop- en dempcommando's die die speler ondersteunt: stop, of pauze als hij geen stop heeft, of uitzetten als hij geen van beide heeft; dempen, of volume op 0 als hij niet kan dempen. `volume_step` is het aantal procentpunten van één druk, van 1 tot 20, en begint op 5 (vermijdt overmatig drukken op de DSM). Het wordt bewaard wanneer de speler volumecommando's kan aanvaarden. Kan de speler aangezet worden, dan stuurt een "afspelen" commando eerst `turn_on` terwijl die speler uit of in standby staat, en daarna `media_play`. Een bronknop blijft alleen `select_source` zonder inschakelen. Een speler zonder dempen en zonder volume zetten kan toch gekoppeld worden, en dempen doet dan niets met die speler. Is de bronnenlijst leeg, zet de speler dan aan en open het scherm opnieuw. Bij het wijzigen van dezelfde speler, terwijl die niets meldt, blijven de eerder gekozen namen en commando's beschikbaar.


## WSM

`type: wsm`. De sensor toont de windsnelheid in km/h van 0 tot 50.

## BM8

`type: bm8`. Acht knoppen laten elk een ingebouwde beltoon klinken. De negende knop stopt het geluid. De groep is meestal 1. Een automatisering in HA laat eender welke beltoon klinken met `button.press`.

## Status opvragen (`check_status`)

Voor schakelaars, alleen-lezen, rolluiken, sferen, … kun je bij opstarten een bus-**Status** laten sturen om de toestand op te vragen. Staat `check_status` uit, dan herstellen schakelaars en alleen-lezen sensoren de laatste aan/uit-stand en bevragen ze de bus niet. Rolluiken en sferen doen dat (nog) niet.

## SoftM en bus repeater

Hoofdschakelaars staan in de **integratie-instellingen**:

- SoftM status-tracking → [SoftM](/SoftM.html)  
- TCP bus repeater → [Bus-repeater](/Bus-repeater.html)  
