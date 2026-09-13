# AH Laatste Kans scanner

Publieke authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Architectuur

- De primaire scheduler is één supervised GitHub Actions-sessie die om circa 17:00 Europe/Amsterdam start en tot na 22:30 actief blijft. De vroege start geeft 30 minuten marge voor GitHub-schedulervertraging.
- Binnen die sessie worden raw metingen exact iedere 3 minuten uitgevoerd van 17:30 t/m 22:30: 101 meetpunten.
- Aanvullende exacte vijfminutenpunten worden alleen uitgevoerd waar die niet al met de 3-minutenreeks samenvallen. De union bevat 141 scans en levert een afzonderlijke canonical reeks van 61 exacte vijfminutenmetingen.
- GitHub Actions benadert AH uitsluitend met `AH_REFRESH_TOKEN`; anonymous auth is uitgeschakeld.
- `scanner.py` bewaart het exacte bedoelde meetpunt in `scheduledAt`/`scheduledSlot` én `rawScheduledAt`/`rawScheduledSlot`; er wordt niets naar een ander tijdslot afgerond.
- `scripts/publish.py` is de enige persistence-/pushroute. Hij reset bij een pushrace naar de actuele `main`, past de meting opnieuw toe en probeert maximaal drie keer.
- `scripts/persist.py` accepteert alleen `user-refresh`, `valid=true`, status `OK`/`OK_ZERO_ROWS`, alle drie winkels fetched en categorie exact `Vlees`.
- `data/YYYY-MM-DD.jsonl` bewaart alle geldige metingen. `data/today.json` bevat uitsluitend de 61 exact gemeten canonical vijfminutenpunten; ontbrekende slots blijven ontbrekend.

## Zelfherstel

De scanner heeft drie lagen herstel zonder alternatieve datalogica:

1. `scanner.py` herhaalt tijdelijke HTTP/netwerkfouten en store-fetches met begrensde backoff.
2. De supervised sessie probeert een mislukt meetpunt lokaal opnieuw zolang het oorspronkelijke tijdstip nog binnen de harde 240-secondenvaliditeitsgrens valt. Ook een tijdelijke publishfout wordt opnieuw geprobeerd zonder een ander tijdslot te verzinnen.
3. Een onafhankelijke watchdog gebruikt twee staggered vijfminutencrons en controleert daardoor iedere 2–3 minuten welke 3- of 5-minutenmeetpunten nog ontbreken en nog eerlijk kunnen worden hersteld. Hij dispatcht altijd dezelfde `scanner.yml` met het oorspronkelijke tijdstip.

Ongeldige, anonymous, `FAILED` of `INCOMPLETE` metingen worden nooit als geslaagd opgeslagen. Daardoor blijft zo'n meetpunt voor de watchdog automatisch "missing" en wordt herstel getriggerd zolang dat nog eerlijk kan.

## Cloudflare

Cloudflare is alleen een stateless relay voor de openbare, gevalideerde scannerdata. Cloudflare:

- benadert AH nooit rechtstreeks;
- bevat geen GitHub-token en dispatcht geen workflows;
- heeft geen Cron Trigger nodig;
- relayeert `/health`, `/probe`, `/data/today`, `/slot` en `/official-1925` vanuit deze repository.

Daarmee zit Cloudflare niet in het kritieke fetch- of schedulerpad.

## Diagnostiek

- `probe.py` is een zero-persistence live probe en gebruikt exact dezelfde token- en store-fetchlogica als productie.
- De probe compileert alle productiecode, draait `scripts/selftest.py` en controleert vervolgens live `user-refresh`, alle drie winkels en categorie `Vlees` zonder productiedata te overschrijven.
- `scripts/selftest.py` verifieert 101 raw punten, 61 canonical punten, de 141-punts union, persistence-validatie en watchdogdekking.
- De probe draait onafhankelijk rond 12:18 Europe/Amsterdam en wordt ook uitgevoerd na wijzigingen aan scanner-, sessie-, persistence- of watchdogcode.

## Winkels

- 1463 — AH Blekersvaartweg
- 1348 — AH Zandvoortselaan
- 1135 — AH Casablancastraat

Alleen `categoryTitle == Vlees` telt als vlees; `Vleeswaren` valt erbuiten.

## Kosten en duurzaamheid

De scannerrepository is publiek en gebruikt uitsluitend standaard GitHub-hosted runners. Voor publieke repositories zijn deze runners gratis; er zijn geen larger runners, artifacts of betaalde externe schedulers nodig. De private `FolderDeal`-repository voert geen AH-scans via GitHub Actions uit. Cloudflare doet alleen on-demand relaywerk en heeft geen cronverbruik voor de scanner.

De supervised sessie heeft een timeout van 350 minuten. Bij een normale start rond 17:00 wacht hij tot 17:30 en eindigt kort na 22:30, dus binnen de zes-uurslimiet van een standaard GitHub-hosted job.
