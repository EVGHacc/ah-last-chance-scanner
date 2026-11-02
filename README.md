# AH Laatste Kans scanner

Publieke authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Productiepad en scheduling

1. Alleen `.github/workflows/session.yml` bezit de productieplanning en start de supervised sessie.
2. `scripts/schedule_gate.py` accepteert uitsluitend bedoelde starts binnen het venster 17:30–22:30 Europe/Amsterdam, met CET/CEST-correctie.
3. `scripts/session.py` plant de volledige union van 3- en 5-minutenpunten tussen 17:30 en 22:30.
4. `scanner.py` haalt de winkels authenticated op met uitsluitend `user-refresh`.
5. `scripts/publish.py` is de productie-schrijfroute en gebruikt `scripts/persist.py` voor validatie en opslag.

De productieconcurrency is `ah-production-single-writer` met `cancel-in-progress: false`. Een nieuwe scheduler-run mag een lopende sessie niet annuleren.

## Watchdog en guardian

`.github/workflows/fallback-qa.yml` is uitsluitend een read-only watchdog. Deze controleert de actieve primaire sessie en de meest recente gepubliceerde scan. De watchdog mag geen workflow annuleren, dispatchen, token wijzigen of productiegegevens publiceren. Een ontbrekende sessie of ongeldige/verouderde scan resulteert in ALARM.

`.github/workflows/guardian.yml` voert uitsluitend regressietests uit bij relevante codewijzigingen. Het is geen tweede productie-scheduler of publisher.

De watchdog controleert de versheid van de laatst gepubliceerde scan (maximaal 240 seconden). Dit is nadrukkelijk geen onafhankelijke proces-heartbeat; een afzonderlijke heartbeat met een alarmgrens van 60 seconden vereist een aparte, atomische heartbeatbron en valt buiten deze scheduler/watchdog-wijziging.

## Meetreeks

- raw: iedere 3 minuten, 17:30–22:30, exact 101 punten;
- canonical: iedere 5 minuten, 17:30–22:30, exact 61 punten;
- union: 141 daadwerkelijke scans doordat beide reeksen iedere 15 minuten samenvallen;
- winkels: 1463 Blekersvaartweg, 1348 Zandvoortselaan, 1135 Casablancastraat;
- categorie: exact `Vlees`; `Vleeswaren` telt niet mee.

Een observatie telt alleen bij `user-refresh`, `valid=true`, `OK`/`OK_ZERO_ROWS`, maximaal 240 seconden vertraging en succesvolle fetch van alle drie winkels.

## Opslag

- `data/YYYY-MM-DD.jsonl`: verliesvrije geldige observaties van die dag;
- `data/latest.json`: laatste geldige observatie;
- `data/today.json`: compacte canonical Vlees-reeks, maximaal 61 punten;
- `data/status.json`: actuele dagcompleetheid;
- `data/days/YYYY-MM-DD.status.json`: gearchiveerde dagcompleetheid vanaf invoering van deze controle;
- `data/central/`: bronmanifest, legacy-data en afgeleide analyses.

`data/today.json` wordt nooit gevuld met terugberekende of oudere waarnemingen. Ontbrekend blijft ontbrekend.

## Authenticatie

De productie gebruikt `AH_REFRESH_TOKEN` als GitHub Actions Secret. Een geroteerde refresh-tokenstate wordt versleuteld in `data/auth_state.enc`, zodat opeenvolgende scannerprocessen dezelfde sessie veilig kunnen voortzetten.

## Cloudflare

Cloudflare zit niet in het kritieke scanpad. De Worker benadert AH niet, bevat geen AH- of GitHub-token, start geen GitHub Actions, schrijft geen scannerdata en relayeert alleen reeds gepubliceerde GitHub-data.
