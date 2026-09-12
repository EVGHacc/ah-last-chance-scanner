# AH Laatste Kans scanner

Publieke authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Architectuur

- Cloudflare Worker is de klok: raw scans worden iedere 3 minuten tussen 17:30 en 22:30 Europe/Amsterdam gedispatcht.
- Aanvullende Cloudflare-triggers vullen alleen de vijfminutengrenzen aan die niet samenvallen met de 3-minutenreeks, zodat alle 61 canonical momenten exact kunnen worden gemeten.
- GitHub Actions voert de AH-call uit met `AH_REFRESH_TOKEN`; anonymous auth is bewust uitgeschakeld.
- `scanner.py` bewaart zowel de echte trigger (`rawScheduledAt`/`rawScheduledSlot`) als de bijbehorende canonical vijfminutenslot.
- `scripts/persist.py` accepteert alleen `user-refresh`, `valid=true`, status `OK`/`OK_ZERO_ROWS`, alle drie winkels fetched en categorie `Vlees`.
- `data/YYYY-MM-DD.jsonl` bewaart alle geldige raw metingen, inclusief de aanvullende exact-canonical triggers.
- `data/today.json` is de canonical 61-slot reeks (17:30–22:30). Een canonical observatie telt alleen als `rawScheduledSlot` exact gelijk is aan `scheduledSlot`; ontbrekende slots blijven ontbrekend en worden nooit gefabriceerd.
- De watchdog controleert iedere 5 minuten freshness, auth, status, winkels en categorie en voert bij afwijkingen een authenticated recovery scan uit. Recovery herstelt de actuele keten, maar vult geen historische missers achteraf in.
- Cloudflare relayeert uitsluitend deze authenticated GitHub-data en vraagt AH niet rechtstreeks uit.
- Een dagelijkse zero-persistence live probe controleert onafhankelijk dat de token en alle drie winkels nog werken zonder productiedata te wijzigen.

## Kosten

Deze repository is publiek en gebruikt alleen standaard `ubuntu-latest` GitHub-hosted runners. Er worden geen betaalde/larger runners gebruikt. De private `FolderDeal`-repository voert geen AH-scans via GitHub Actions uit.
