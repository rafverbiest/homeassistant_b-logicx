---
layout: default
lang: nl
title: "Installatie"
description: "Installeren via HACS of met de hand, en daarna de gateway toevoegen."
last_modified_at: 2026-10-15
alternate: /Installation.html
permalink: /Installatie.html
---

# Installatie

**Nederlands** · [English](/Installation.html) · [← Home](/)

## Via HACS (aanbevolen)

1. Installeer [HACS](https://hacs.xyz/) als je dat nog niet hebt.
2. In Home Assistant: **HACS** → rechtsboven **⋮** → **Custom repositories**.
3. Repository-URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Categorie: **Integration**
4. **Add** → zoek **B-Logicx** → **Download**.
5. **Herstart** Home Assistant.
6. **Instellingen → Apparaten en diensten → Integratie toevoegen → B-Logicx**.
7. Vul het **IP-adres** van de NWM / NWX in (standaardpoort `10001`).

Zie ook de [README](https://github.com/rafverbiest/homeassistant_b-logicx#installeren-met-hacs-custom-repository).

## Handmatig (zonder HACS)

1. Kopieer de map `custom_components/b_logicx` naar je HA-`config/custom_components/`-directory.
2. Herstart Home Assistant.
3. Voeg de integratie toe zoals hierboven (stap 6–7).

## Eerste configuratie

Na toevoegen van de integratie:

- Stel **adressen** in via de opties-UI (toevoegen / bewerken / verwijderen), of  
- Importeer een YAML-bestand ([YAML](/YAML.html), sjabloon: `custom_components/b_logicx/flow/template.yaml`).

Optioneel later: SoftM status-tracking en TCP bus repeater in de **integratie-instellingen** — zie [SoftM](/SoftM.html) en [Bus-repeater](/Bus-repeater.html).
