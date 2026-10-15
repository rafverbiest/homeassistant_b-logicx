---
layout: default
lang: en
title: "YAML import / export"
description: "Import and export addresses as YAML."
last_modified_at: 2026-10-15
alternate: /YAML.html
permalink: /YAML-en.html
---

# YAML import / export

[Nederlands](/YAML.html) · **English** · [← Home](/en.html)

Addresses can be managed in the UI or as YAML.

## Template

The integration ships with a sample:

`custom_components/b_logicx/flow/template.yaml`

The repo also has `examples/demo_site.yaml`.

## Import

In the integration options: import YAML (upload a file). Invalid combinations are rejected.

## Export

From options you can export the current configuration and download it.

## Tips

- In the UI, bus members are sorted by group first, then by address (covers by open pair; Sfeer by room group).  
- SoftM fields: see [SoftM](/SoftM-en.html).  
- After an export/import round-trip, use `blxmonitor` to confirm bus behaviour — [Diagnostics](/Diagnostics.html).
