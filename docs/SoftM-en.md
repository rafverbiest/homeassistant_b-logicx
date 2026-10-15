---
layout: default
lang: en
title: "SoftM (virtual status module)"
description: "Virtual status module for Software Members."
last_modified_at: 2026-10-15
alternate: /SoftM.html
permalink: /SoftM-en.html
---

# SoftM (virtual status module)

[Nederlands](/SoftM.html) · **English** · [← Home](/en.html)

Home Assistant can act as a **virtual status module (VSM)** for Software Members (SoftM) — similar to a hardware STM.

## Bus behaviour

| Bus command | Action |
|-------------|--------|
| **Toggle** | Flip memory, emit **Set** or **Reset** (cancels SoftM timer) |
| **Status** | Reply with **Set** / **Reset** from memory (**does not** cancel SoftM timer) |
| **Timer** (optional) | **Set**, wait `softm_timer` seconds, then **Reset**. Similar to the INM *software member timer*, but better: this timer *does* obey a **Reset** command — a frustrating limitation of real SoftM timers. |

## Enabling

Both required:

1. **Integration settings** → *Enable SoftM status tracking*
2. Per address: `enable_softm_status_tracking: true` (optional `softm_timer`, `persist_state`, `default_state`)

## Important rules

- Do **not** combine SoftM tracking with `check_status` on the same address (YAML/UI reject that). You cannot be the status module for an address and also poll Status from the bus at the same time: that Status command would have to be answered by yourself, which makes no sense.
- Do **not** enable SoftM tracking if a hardware **STM** already tracks that SoftM address.
- SoftM addresses **must** use `on_command: Set` and `off_command: Reset`. Toggle (or any other command) is rejected: the virtual status module already answers bus Toggle (and Timer), and that answer is always Set or Reset.
