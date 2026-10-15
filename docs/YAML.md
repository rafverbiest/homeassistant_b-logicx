---
layout: default
lang: nl
title: "YAML import / export"
description: "Adressen importeren en exporteren als YAML."
last_modified_at: 2026-10-15
alternate: /YAML-en.html
permalink: /YAML.html
---

# YAML import / export

**Nederlands** · [English](/YAML-en.html) · [← Home](/)

Adressen kun je beheren in de UI of als YAML.

## Sjabloon

In de integratie zit een voorbeeld:

`custom_components/b_logicx/flow/template.yaml`

Er is ook `examples/demo_site.yaml` in de repo.

## Import

In de integratie-opties: YAML importeren (bestand uploaden). Ongeldige combinaties worden geweigerd.

## Export

Via de opties kun je de huidige configuratie exporteren en downloaden.

## Tips

- In de UI staan busmembers eerst gesorteerd op groep, dan op adres (rolluik op open-paar; Sfeer op kamergroep).  
- SoftM-velden: zie [SoftM](/SoftM.html).  
- Na een export/import-rondje kun je met `blxmonitor` controleren of de bus zich gedraagt zoals verwacht — [Diagnostiek](/Diagnostiek.html).
