# B-Logicx voor Home Assistant

**Nederlands** | [English](README.en.md)

Custom integration voor **[B-Logicx](https://b-logicx.be/)**: RLM's, dimmers, rolluiksturingen, sferen, readonly adressen (generiek Set/Reset), Software members, VSM (Virtuele Status Module), RTC (Real-Time Clock), LDM (Lichtsensor), TSM (Temperatuursensor), WSM (Windsnelheidsmonitor), BM8 (Belmodule) en een TCP bus repeater. Verbindt rechtstreeks met de NWM/NWX. Geen B-Logicx Home Server nodig. Onafhankelijk van de fabrikant.

**B-Logicx officiële website:** [b-logicx.be](https://b-logicx.be/) ·
**Website van deze integratie:** [b-logicx.rafverbiest.be](https://b-logicx.rafverbiest.be) ·
**Releases:** [changelog](https://github.com/rafverbiest/homeassistant_b-logicx/releases)

## Installeren met HACS

1. Installeer [HACS](https://hacs.xyz/) als je dat nog niet hebt (of kies 'marketplace' bij Home Assistant versie 2026.11 of hoger)
2. Zoek **B-Logicx** in HACS en kies **Download**.
   Staat het er nog niet bij, voeg de repository dan eerst toe via **HACS** → rechtsboven **⋮** → **Custom repositories**:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Categorie: **Integration**. Klik **Add**, zoek **B-Logicx** en kies **Download**.
3. **Herstart** Home Assistant.
4. **Instellingen → Apparaten en diensten → Integratie toevoegen → B-Logicx** en vul het IP van je gateway in (standaardpoort `10001`).

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
