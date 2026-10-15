---
layout: default
lang: nl
title: "SoftM (virtuele statusmodule)"
description: "Virtuele statusmodule voor Software Members."
last_modified_at: 2026-10-15
alternate: /SoftM-en.html
permalink: /SoftM.html
---

# SoftM (virtuele statusmodule)

**Nederlands** · [English](/SoftM-en.html) · [← Home](/)

Home Assistant kan als **virtuele statusmodule (VSM)** optreden voor Software Members (SoftM) — vergelijkbaar met een hardware STM.

## Busgedrag

| Buscommando | Actie |
|-------------|--------|
| **Toggle** | Geheugen omklappen, **Set** of **Reset** uitzenden (annuleert SoftM-timer) |
| **Status** | Antwoorden met **Set** / **Reset** uit geheugen (**annuleert de SoftM-timer niet**) |
| **Timer** (optioneel) | **Set**, wacht `softm_timer` seconden, daarna **Reset**. Vergelijkbaar met de INM *software member timer*, maar beter: deze timer gehoorzaamt wél een **Reset**-commando — een vervelende tekortkoming van echte SoftM-timers. |

## Inschakelen

Beide nodig:

1. **Integratie-instellingen** → *SoftM status-tracking inschakelen*
2. Per adres: `enable_softm_status_tracking: true` (optioneel `softm_timer`, `persist_state`, `default_state`)

## Belangrijke regels

- SoftM-tracking **niet** combineren met `check_status` op hetzelfde adres (YAML/UI weigeren dat). Je kan onmogelijk tegelijk de statusmodule zijn voor een adres én de status opvragen aan de bus: dat Status-commando zou dan door jezelf moeten worden beantwoord, wat geen steek houdt.
- SoftM-tracking **niet** inschakelen als een hardware **STM** dat SoftM-adres al volgt.
- SoftM-adressen **moeten** `on_command: Set` en `off_command: Reset` gebruiken. Toggle (of een ander commando) wordt geweigerd: de virtuele statusmodule beantwoordt bus-Toggle (en Timer) al, en dat moet logischerwijze altijd met Set en Reset.
