# AH Laatste Kans scanner

Publieke authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Productiepad

1. `.github/workflows/session.yml` start één supervised sessie rond 17:00 Europe/Amsterdam.
2. `scripts/session.py` plant de volledige union van 3- en 5-minutenpunten tussen 17:30 en 22:30.
3. `scanner.py` haalt alle drie winkels authenticated op met uitsluitend `user-refresh`.
4. `scripts/publish.py` is de enige schrijf-/pushroute en gebruikt `scripts/persist.py` voor validatie en opslag.
5. Cloudflare leest de openbare gevalideerde GitHub-output alleen als stateless relay.

Er is bewust geen tweede scheduler, watchdog of recovery-workflow meer. De supervised sessie detecteert zelf recente gaten, probeert ze binnen de harde 240-secondenvaliditeitsgrens te herstellen en voert na 22:30 een eindcontrole uit.

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

## Herstel en controles

`session.py` probeert een mislukt scan- of publishpunt opnieuw zolang het oorspronkelijke tijdstip nog geldig kan worden gemeten. Voor en na meetpunten controleert de sessie de gepubliceerde status op recente gaten. Na 22:30 moet de eindstatus exact `101/101 raw` en `61/61 canonical` zijn; anders faalt de workflow met de exacte ontbrekende slots.

`probe.yml` compileert en test de productiecode en doet rond het middaguur een zero-persistence live authenticated probe. `scripts/central_data_check.py` controleert de continuïteit van de huidige dagbestanden en maakt de bekende overgang tussen legacy- en huidige data expliciet.

## Cloudflare

Cloudflare zit niet in het kritieke scanpad. De Worker:

- benadert AH niet;
- bevat geen AH- of GitHub-token;
- start geen GitHub Actions;
- schrijft geen scannerdata;
- relayeert alleen reeds gepubliceerde GitHub-data.

## Authenticatie

De productie gebruikt `AH_REFRESH_TOKEN` als GitHub Actions Secret. Een geroteerde refresh-tokenstate wordt versleuteld in `data/auth_state.enc`, zodat opeenvolgende scannerprocessen dezelfde sessie veilig kunnen voortzetten.
