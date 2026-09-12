# AH Laatste Kans scanner

Publieke, authenticated runner voor de AH Laatste Kans-scanner. Gevoelige configuratie staat uitsluitend in GitHub Actions Secrets.

## Architectuur

- Cloudflare Worker is de klok: iedere 3 minuten tussen 17:30 en 22:30 Europe/Amsterdam dispatcht hij `scanner.yml`.
- GitHub Actions voert de AH-call uit met `AH_REFRESH_TOKEN`; anonymous auth is bewust uitgeschakeld.
- `scanner.py` bewaart de raw trigger (`rawScheduledAt`) en koppelt elke raw scan daarnaast eerlijk aan de voorafgaande 5-minutenslot voor de timinganalyse.
- `scripts/persist.py` accepteert alleen `user-refresh`, `valid=true`, status `OK`/`OK_ZERO_ROWS`, alle drie winkels fetched en categorie `Vlees`.
- `data/today.json` is de canonical 61-slot reeks (17:30–22:30); ontbrekende slots blijven ontbrekend en worden nooit gefabriceerd.
- De watchdog controleert iedere 5 minuten freshness, auth, status, winkels en categorie en voert bij afwijkingen een authenticated recovery scan uit.
- Cloudflare relay/mirror leest uitsluitend deze authenticated GitHub-data; Cloudflare vraagt AH niet rechtstreeks uit.

## Kosten

Deze repository is publiek en gebruikt alleen standaard `ubuntu-latest` GitHub-hosted runners. GitHub documenteert standaard runners voor publieke repositories als gratis. Er worden geen betaalde/larger runners gebruikt.
