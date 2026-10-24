---
layout: default
lang: en
title: "Dimmer"
description: "A dimmer as a light, with a slider and a short on/off tap."
last_modified_at: 2026-10-24
alternate: /Dimmer.html
permalink: /Dimmer-en.html
---

# Dimmer

[Nederlands](/Dimmer.html) · **English** · [← Home](/en.html)

A dimmer is normally addressed in group 5, 6, 7, 8 or 9. That group defines the room. Sfeer entries are gathered per group, and therefore per room.

Home Assistant shows an individual dimmer as one light: a master switch and a slider from 0 to 100. On and off send a `Dimmer` command to that address, followed by `Dimmer` again to the fixed address 220. The dimmer itself answers with `Set` or `Reset`. The protocol lets you leave time between the two commands, time in which the dimmer starts dimming up and down. The idea is that you release at the wanted level, but that is not very usable through Home Assistant, so the two commands follow each other immediately.

There are 3 ways to control dimmers:

1. With Sfeer
2. Individually
3. With scenes via Home Assistant. This is the same as item 1, except that HA takes over B-Logicx Sfeer control and drives the dimmers individually. Have the INMs toggle a software member, which an HA automation then follows to call the right scene. You can also include other actions, such as closing the curtains or turning on the TV.

All of these can be used together, but I would choose to do it only through Sfeer or scenes where possible. Because of the technical limits of the B-Logicx protocol, it is hard for Home Assistant to know the dimmer's set light level in percent. Home Assistant can set the dimmer to a requested percentage. A short tap leaves that percentage in place, but once the level is changed with an INM (for example by holding the button and releasing at the right moment) the percentage shown in HA is unknown afterwards, because it cannot be read back from the bus.

## What a B-Logicx Sfeer is (set up via BLConfig)

A Sfeer is a recorded setting for the dimmers that share a group. You set the dimmers to a good level by hand and then record the Sfeer. It then sits at address 221 through 228. At most eight per room.

This integration calls a Sfeer by sending `Dimmer` to `<group> 221`–`228`. The dimmers that take part answer themselves with `Set` or `Reset` on their own address. That answer shows which lamp is on. We do not know the recorded percentage, but we do know which of the at most eight Sfeer entries is active.

Some dimmers also send `Set` or `Reset` to particular RLMs or SoftMs when a Sfeer runs, from a condition saved with that Sfeer. That normally goes through BLConfig, but automations can do it through HA as well.

## Why a slider

Finding a good level by holding the button is not a pleasant daily control. With many LED lamps the useful range sits in a small slice of the actual operating range, and because of the delay on the bus you release the button too late. With the slider you can send a value in percent, either by hand or through automations.

## Options configured in BLConfig that HA should know too

| Option | YAML | Default |
|--------|------|---------|
| Memo | `remembers_level` | off |
| Participates in Sfeer | `participates_in_moods` | on |
| Ask for state at startup | `check_status` | off |

Memo means the module remembers the dim level when off. With `check_status` off, Home Assistant shows the last on/off and the last percent after a restart. Turning it on asks the bus for on or off only, because the percent cannot be read back due to technical limits in B-Logicx.

```yaml
- type: dimmer
  name: Table lamp
  group: 5
  address: 40
  remembers_level: false
  participates_in_moods: true
  check_status: false
```
