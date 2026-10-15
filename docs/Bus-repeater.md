---
layout: default
lang: nl
title: "TCP bus repeater"
description: "De ene NWM-verbinding delen met BLConfig."
last_modified_at: 2026-10-15
alternate: /Bus-repeater-en.html
permalink: /Bus-repeater.html
---

# TCP bus repeater

**Nederlands** · [English](/Bus-repeater-en.html) · [← Home](/)

NWM / NWX aanvaarden **één** TCP-client. Met de repeater houdt Home Assistant die ene link open en luistert op HA (standaardpoort `10001`), zodat **BLConfig** / **blxmonitor** op hetzelfde LAN-subnet als de NWM de bus kunnen delen.

## Inschakelen

1. **Integratie-instellingen** → *TCP bus repeater inschakelen* (poort standaard `10001`).
2. Richt BLConfig / blxmonitor op het **Home Assistant-IP**, niet op het gateway-IP.  
   Op de HA-host zelf mag je `127.0.0.1` gebruiken (localhost is altijd toegelaten).

## Toegang

In de integratie-instellingen vul je een **CIDR** in (bijvoorbeeld `192.168.50.0/24`). Alleen clients in dat subnet worden toegelaten.

- **Localhost** (loopback): altijd toegelaten.  
- Leeg subnet: oud gedrag (de `/24` van het gateway-adres).


## Zonder repeater

Zonder deze functie heb je een tweede NWM/NWX of een **NWM2** nodig om HA en BLConfig tegelijk te gebruiken.

## Waarschuwing

De repeater is nog weinig getest. Gebruik hem voorlopig **niet** als enige pad voor kritieke **Program**-acties door BLConfig.
