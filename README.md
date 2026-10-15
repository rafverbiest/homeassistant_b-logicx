# B-Logicx voor Home Assistant

**Nederlands** | [English](README.en.md)

Custom integration voor de **[B-Logicx](https://b-logicx.be/) (NWM / NWX)** bus-gateway: RLM's, dimmers, rolluiksturingen, sferen, readonly adressen, SoftM VSM, RTC, LDM/TSM/WSM, BM8 en een TCP bus repeater. Onafhankelijk van de fabrikant.

**B-Logicx:** [b-logicx.be](https://b-logicx.be/) ·
**Site:** [b-logicx.rafverbiest.be](https://b-logicx.rafverbiest.be) ·
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

Configureer adressen in de integratie-opties (UI) of via YAML-import. Sjabloon: `custom_components/b_logicx/flow/template.yaml`.

## Handmatige installatie

Kopieer `custom_components/b_logicx` naar je HA-`config/custom_components/`, herstart, en voeg de integratie toe zoals hierboven.

## Verder lezen

- [Installatie](https://b-logicx.rafverbiest.be/Installatie.html) · [Configuratie](https://b-logicx.rafverbiest.be/Configuratie.html)
- [Dimmer](https://b-logicx.rafverbiest.be/Dimmer.html) · [SoftM](https://b-logicx.rafverbiest.be/SoftM.html) · [Bus-repeater](https://b-logicx.rafverbiest.be/Bus-repeater.html)
- [Diagnostiek](https://b-logicx.rafverbiest.be/Diagnostiek.html) (`blxmonitor`) · [YAML](https://b-logicx.rafverbiest.be/YAML.html) · [B-Logicx upgrades](https://b-logicx.rafverbiest.be/Alternatieven.html)

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
