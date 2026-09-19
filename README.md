# B-Logicx voor Home Assistant

**Nederlands** | [English](README.en.md)

Custom integration voor de **B-Logicx (BL-NWM)** bus-gateway: RLM's, rolluiksturing (dubbele RLM), Dimmersferen, Read-Only adressen (RLM/SoftM), RTC-kloksynchronisatie, LDM-lichtsensoren, TSM-temperatuursensoren, SoftM Virtuele Status Module en een TCP bus repeater.

**0.9.5.4:** SoftM `softm_timer` wordt niet meer gestopt door SoftM’s eigen Set-echo’s (Timer-start / Status-antwoord); Status commando tijdens de timer antwoordt Set en onderbreekt de timer niet. Reset onderbreekt onmiddellijk.

**0.9.5.3:** Bus repeater laat localhost toe; `blxmonitor` verplaatst naar de b_logicx library submap; timestamps met datum (`YYYY-MM-DD HH:MM:SS.mmm`).

**0.9.5.2:** `blxmonitor` `-l`/`--log-file` schrijft elke TX/RX-regel op het scherm mee naar een logfilel; handig voor long-term debugging via de TCP bus repeater (in bijvoorbeeld tmux/screen).

## Installeren met HACS (custom repository)

1. Installeer [HACS](https://hacs.xyz/)
2. Open in Home Assistant **HACS** → rechtsboven **⋮** → **Custom repositories**.
3. Repository-URL:

   ```text
   https://github.com/rafverbiest/homeassistant_b-logicx
   ```

   Categorie: **Integration**
4. Klik **Add**, zoek **B-Logicx** in HACS en kies **Download**.
5. **Herstart** Home Assistant.
6. **Instellingen → Apparaten en diensten → Integratie toevoegen → B-Logicx** en vul het IP van je gateway in (standaardpoort `10001`).

Na installatie configureer je adressen in de integratie-opties (UI) of via YAML-import. Er zit een template bij:

`custom_components/b_logicx/template.yaml`

## Handmatige installatie (zonder HACS)

Kopieer de map `custom_components/b_logicx` naar je HA-`config/custom_components/`-directory, herstart, en voeg daarna de integratie toe zoals hierboven.

## SoftM status-tracking (v0.9+)

Home Assistant kan als **virtuele statusmodule** optreden voor Software Members (SoftM):

- Bus **Toggle** → verander geheugen-status en **Set** / **Reset** uitzenden als antwoord (annuleert SoftM-timer)
- Bus **Status** → antwoorden met **Set** / **Reset** uit geheugen (**annuleert SoftM-timer niet**)
- Optioneel bus-**Timer**-commando → **Set**, wacht `softm_timer` seconden, daarna **Reset** (`softm_timer` is geen HA auto-off)
- Externe / HA **Set** / **Reset** werkt het geheugen bij en annuleert de SoftM-timer

Beide inschakelen:

1. **Integratie-instellingen** → *SoftM status-tracking inschakelen*
2. Per adres: `enable_softm_status_tracking: true` (en optioneel `softm_timer`, `persist_state`, `default_state`)

Combineer SoftM-tracking **niet** met `check_status` op hetzelfde adres (YAML/UI weigeren dat). Schakel SoftM-tracking **niet** in als een hardware BL-STA dat SoftM busadres reeds volgt. SoftM-adressen **moeten** `on_command: Set` en `off_command: Reset` gebruiken — Toggle (of een ander commando) wordt geweigerd bij YAML-import én in de config flow (VSM beantwoordt bus-Toggle al; HA-Toggle zou dubbel omschakelen).

## TCP bus repeater (v0.9)

BL-NWM / BL-NMX aanvaarden **één** TCP-client. Met de repeater aan houdt HA die ene verbinding open en luistert op HA (standaardpoort `10001`), zodat **BLConfig** / **blxmonitor** op hetzelfde LAN-subnet als de NWM de bus kunnen delen.

1. **Integratie-instellingen** → *TCP bus repeater inschakelen* (poort standaard `10001`)
2. Richt BLConfig / blxmonitor op het **Home Assistant-IP**, niet op het gateway-IP (of `127.0.0.1` als je op de HA-host zelf draait)

Clients buiten de `/24` van de NWM worden geweigerd, behalve **localhost** (loopback).

Met gewone B-Logicx-gateways zoals BL-NWM/NWX kun je maar één verbinding openen!
Terwijl de integratie draait, heeft zowel blxmonitor als de officiële BLConfig Windows-software een tweede verbinding nodig die alleen beschikbaar is met een dure BL-NWM2.

De TCP repeater lost dat op. Opgelet: deze functie is weinig getest, voorlopig geen aanrader om je BLConfig software langs deze repeater te verbinden en kritische Program's uit te voeren ;) 

## Diagnostiek

`blxmonitor.py` (busmonitor / command line zit in de shared b_logicx library:

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-of-gateway-ip> -p 10001
```

Program-verkeer (meestal BLConfig) wordt standaard getoond; gebruik `--hide-program` om het te filteren. Met de bus repeater aan: gebruik de Home Assistant-host als `-i`.

Om elke TX/RX-regel op het scherm (met timestamp) vast te leggen voor het traceren van zeldzame fouten:

```bash
python3 /config/custom_components/b_logicx/b_logicx/blxmonitor.py -i <ha-of-gateway-ip> -p 10001 -l /config/blxbus.log
```

Regels worden geappend (zelfde formaat als de terminal). Handig als je `blxmonitor` onder `screen`/`tmux` laat lopen via de TCP bus repeater.


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
