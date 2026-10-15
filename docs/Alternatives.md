---
layout: default
lang: en
title: "B-Logicx upgrades"
description: "What Home Assistant takes over from older B-Logicx modules."
last_modified_at: 2026-10-15
alternate: /Alternatieven.html
permalink: /Alternatives.html
---

# B-Logicx upgrades

[Nederlands](/Alternatieven.html) · **English** · [← Home](/en.html)

## Some modules are no longer needed

With a **NWM / NWX** and this Home Assistant integration, HA is already on the B-Logicx bus. That means a separate B-Logicx WiFi path for switches is no longer needed.

**ST2**, **ST4**, and **WRL** provide a way to link B-Logicx to a (dedicated) WiFi network and control switches or actions remotely.

Because this integration monitors and controls the bus directly, for *new* wireless switches and actuators you can often choose what Home Assistant already supports well — for example **Shelly**, **Zigbee**, **Matter**, or another HA integration — and let those work together in HA with your existing B-Logicx members (RLMs, SoftMs, Sfeer, RTC, …).

You then avoid building a second, parallel control network beside the bus; HA is the shared layer.

- **Example:** use a Niko switch with an INM to switch a Shelly or Zigbee socket (very cheap to get on Amazon or at IKEA).

## Automations

### RLM

B-Logicx provides one AND and one OR gate per RLM, as well as a stepper (sequence) automaton.

### INM

Each INM includes a ‘Virtual control’ and a ‘Software Member Timer’.

### This integration

With Home Assistant, much more complex automations become possible — without the same limits, and across technology boundaries. For example:

- With Zigbee window/door sensors: do not allow the roller blind to close while the window is still open, to avoid damage.
- Read the tariff from your digital meter (or online if pricing is set per quarter-hour) and switch non-priority loads via RLMs on and off against threshold values.
- Turn your boiler on or off with an RLM, based on solar-panel yield. Read that directly from the inverter, and even take the weather forecast into account.
