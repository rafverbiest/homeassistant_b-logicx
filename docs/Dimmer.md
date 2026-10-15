---
layout: default
lang: nl
title: "Dimmer"
description: "Een dimmer als lamp, met schuifregelaar en korte aan/uit-puls."
last_modified_at: 2026-10-15
alternate: /Dimmer-en.html
permalink: /Dimmer.html
---

# Dimmer

**Nederlands** · [English](/Dimmer-en.html) · [← Home](/)

Een dimmer is een busmember op een fysieke groep en een fysiek adres. Die groep is de kamer, dezelfde groep als de sferen van die kamer. Home Assistant toont één lamp: een hoofdschakelaar en een schuifregelaar van 0 tot 100. Aan en uit gaat met een korte `Dimmer`-puls naar dat adres, gevolgd door `Dimmer` naar 220. De dimmer antwoordt zelf met `Set` of `Reset`.

<img class="dimmer-card" src="/images/dimmer-nl.png" alt="Meer-info van Tafellamp: helderheid 70 procent, met verticale balk en aan/uit-knop">

Er zijn 3 manieren om dimmers te besturen:
1. Met Sferen
2. Individueel
3. Met Scenes via Home Assistant. Dit is hetzelfde als nr.1 behalve dat HA de sferen-controle van B-Logicx overneemt en de dimmers individueel bedient. Laat de INM's een software member togglen, die dan door een HA-automatisatie wordt gevolgd en de juiste scene oproept. Bovendien kan je dan ook nog andere acties erbij opnemen zoals gordijnen sluiten of de TV inschakelen.

Alle manieren kunnen door elkaar gebruikt worden, maar zelf zou ik kiezen om het alleen via Sferen of Scenes te doen waar mogelijk. Door de technische limitaties van het B-Logicx protocol is het moeilijk voor Home Assistant om de ingestelde lichtwaarde in procent van de dimmer te weten te komen. Home Assistant kan wel de dimmer op een gevraagd percentage zetten. Een korte puls laat dat percentage staan, maar zodra het lichtniveau met een INM wordt aangepast (door bijvoorbeeld lang te drukken en op het goede moment los te laten) dan zal het getoonde percentage in HA daarna onbekend zijn omdat het niet over de bus kan worden ingelezen.

## Wat een B-Logicx sfeer is (instellen via BLConfig)

Een sfeer is een opgenomen instelling voor de dimmers die een groep delen. Je zet de dimmers met de hand op een goed niveau en neemt de sfeer dan op. Ze ligt daarna op adres 221 tot en met 228. Per kamer zijn dat er hoogstens acht.

Deze integratie roept een sfeer op door `Dimmer` naar `<groep> 221`–`228` te sturen. De dimmers die meedoen antwoorden zelf met `Set` of `Reset` op hun eigen adres. Aan dat antwoord zie je welke lamp aan staat. Het opgenomen percentage weten we niet, maar we weten wel welke van de max. 8 sferen actief is.

Sommige dimmers sturen bij een sfeer ook `Set` of `Reset` naar bepaalde RLM's of SoftM's, volgens een voorwaarde die bij die sfeer is opgeslagen. Dat gaat normaal via BLConfig, maar kan via Automatisaties ook via HA.

## Waarom een schuifregelaar

Een goed niveau zoeken door de knop ingedrukt te houden is geen prettige dagelijkse bediening. Bij veel ledlampen zit het bruikbare bereik in een klein stuk van het eigenlijke werkingsbereik, en door de vertraging op de bus laat je de knop te laat los. Door gebruik te maken van de schuifregelaar kan je een waarde in procent sturen, hetzij manueel hetzij via Automatisaties.

## Opties die in BLConfig geconfigureerd worden maar die HA best ook weet

| Optie | YAML | Standaard |
|-------|------|-----------|
| Memo | `remembers_level` | uit |
| Neemt deel aan sferen | `participates_in_moods` | aan |

Memo wil zeggen dat de module het dimniveau onthoudt bij uit.

```yaml
- type: dimmer
  name: Tafellamp
  group: 5
  address: 40
  remembers_level: false
  participates_in_moods: true
```
