# AH Laatste Kans scanner

Publieke authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Architectuur

- Cloudflare Worker is de primaire klok: raw scans worden iedere 3 minuten tussen 17:30 en 22:30 Europe/Amsterdam gedispatcht.
- Aanvullende Cloudflare-triggers vullen alleen de exacte vijfminutengrenzen aan die niet samenvallen met de 3-minutenreeks, zodat alle 61 canonical momenten exact kunnen worden gemeten.
- GitHub Actions benadert AH uitsluitend met `AH_REFRESH_TOKEN`; anonymous auth is uitgeschakeld.
- `scanner.py` bewaart zowel de echte trigger (`rawScheduledAt`/`rawScheduledSlot`) als de bijbehorende canonical vijfminutenslot.
- `scripts/persist.py` accepteert alleen `user-refresh`, `valid=true`, status `OK`/`OK_ZERO_ROWS`, alle drie winkels fetched en categorie exact `Vlees`.
- `data/YYYY-MM-DD.jsonl` bewaart alle geldige raw metingen, inclusief de aanvullende exact-canonical triggers.
- `data/today.json` is de canonical 61-slot reeks (17:30–22:30). Een canonical observatie telt alleen als `rawScheduledSlot` exact gelijk is aan `scheduledSlot`; ontbrekende slots blijven ontbrekend en worden nooit gefabriceerd.

## Zelfherstel

De scanner heeft twee onafhankelijke herstelpaden:

1. Cloudflare controleert twee minuten na ieder bedoeld meetpunt of het resultaat geldig is opgeslagen. Een ontbrekende, stale, anonymous, `FAILED` of `INCOMPLETE` meting wordt opnieuw als authenticated scan voor het oorspronkelijke tijdstip gedispatcht zolang de 240-secondenvaliditeit nog haalbaar is.
2. GitHub heeft daarnaast twee staggered watchdog-crons. Iedere afzonderlijke cron loopt niet vaker dan elke vijf minuten, maar samen controleren ze iedere 2–3 minuten. `scripts/watchdog_targets.py` vindt **alle** ontbrekende 3- en 5-minutenmeetpunten die nog eerlijk binnen de validiteitsmarge kunnen worden hersteld en scant die oudste-eerst. Daardoor blijft herstel mogelijk wanneer de Cloudflare-dispatcher tijdelijk niet werkt.

Scanner- en watchdogworkflows delen één concurrencygroep en de dispatch-workflow controleert eerst of een meetpunt al geldig is opgeslagen. Dubbele calls door race conditions worden daarmee zoveel mogelijk voorkomen.

## Diagnostiek

- Een zero-persistence live probe compileert de scanner, test cadence/persistence/watchdog-invarianten en controleert live `user-refresh`, alle drie winkels en categorie `Vlees` zonder productiedata te overschrijven.
- De probe heeft zowel een Cloudflare-trigger als een onafhankelijke GitHub schedule rond 12:18 Europe/Amsterdam; de GitHub-variant dekt CET en CEST af en gate op het lokale middaguur.
- De probe gebruikt dezelfde token- en store-retrylogica als de productiescanner.

## Winkels

- 1463 — AH Blekersvaartweg
- 1348 — AH Zandvoortselaan
- 1135 — AH Casablancastraat

Alleen `categoryTitle == Vlees` telt als vlees; `Vleeswaren` valt erbuiten.

## Kosten

Deze repository is publiek en gebruikt alleen standaard GitHub-hosted runners. GitHub Actions-minuten voor standaard runners in publieke repositories zijn niet factureerbaar. Er worden geen larger runners gebruikt en er worden geen artifacts/caches voor de AH-scanner bewaard. De private `FolderDeal`-repository voert geen AH-scans via GitHub Actions uit.
