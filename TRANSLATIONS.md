# Translations & terminology (v0.9.3+)

User-facing strings live in:

| File | Role |
|------|------|
| `custom_components/b_logicx/strings.json` | English source of truth |
| `custom_components/b_logicx/translations/en.json` | Keep in sync with `strings.json` |
| `custom_components/b_logicx/translations/nl.json` | Dutch UI |

Home Assistant language **Nederlands** loads `nl.json` for config/options flows, selectors, and entity names that use `translation_key`.

## Glossary (aligned with BLConfig)

| Concept | English UI | Dutch UI |
|---------|------------|----------|
| SoftM, Sfeer, LDM, TSM, RTC, BL-NWM, BL-STA | Unchanged product names | Unchanged |
| Read-only address | Read-only address | Alleen-lezen adres |
| Status / Set / Reset / Toggle / Dimmer | Protocol English | Protocol English |
| Group / Address | Group / Address | Groep / Adres |
| Cover / shutter / blind | Cover / roller / shutter | **Rolluik** |
| Sfeer scene (“mood”) | Sfeer | **Sfeer** (no separate “mood” word) |
| Bus repeater | Bus repeater | **Bus repeater** (English) |
| Sfeer select “Off” | Off | Uit (entity state translation) |

## Config flow UX notes

- Main options menu shows an **entry count** only — not a full dump of members.
- Edit / Remove use a dropdown sorted **group → address** (covers by open pair; Sfeer by room group).
