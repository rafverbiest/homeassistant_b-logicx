# B-Logicx voor Home Assistant

**Nederlands** | [English](README.en.md)

Custom integration voor de **B-Logicx (BL-NWM / BL-NWX)** bus-gateway: schakelaars, rolluiken, Sfeer, alleen-lezen adressen, SoftM VSM, RTC, LDM/TSM en een optionele TCP bus repeater.

**Site:** [b-logicx.rafverbiest.be](https://b-logicx.rafverbiest.be) ·
**Wiki:** [documentatie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki) ·
**Releases:** [changelog](https://github.com/rafverbiest/homeassistant_b-logicx/releases)

## Installeren met HACS (custom repository)

1. Installeer [HACS](https://hacs.xyz/) als je dat nog niet hebt.
2. Open in Home Assistant **HACS** → rechtsboven **⋮** → **Custom repositories**.
3. Repository-URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Categorie: **Integration**
4. Klik **Add**, zoek **B-Logicx** in HACS en kies **Download**.
5. **Herstart** Home Assistant.
6. **Instellingen → Apparaten en diensten → Integratie toevoegen → B-Logicx** en vul het IP van je gateway in (standaardpoort `10001`).

Configureer adressen in de integratie-opties (UI) of via YAML-import. Sjabloon: `custom_components/b_logicx/template.yaml`.

## Handmatige installatie

Kopieer `custom_components/b_logicx` naar je HA-`config/custom_components/`, herstart, en voeg de integratie toe zoals hierboven.

## Verder lezen (wiki)

- [Installatie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Installatie) · [Configuratie](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Configuratie)
- [SoftM](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/SoftM) · [Bus-repeater](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Bus-repeater)
- [Diagnostiek](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/Diagnostiek) (`blxmonitor`) · [YAML](https://github.com/rafverbiest/homeassistant_b-logicx/wiki/YAML)

## Ontwikkeling

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Zie `TESTS.md`, `RELEASING.md` en `TRANSLATIONS.md`.

## Licentie

Zie `LICENSE`.
