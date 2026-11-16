# AH Laatste Kans scanner (v2)

Haalt dagelijks de AH Laatste Kans-aanbiedingen op, vooral **Vlees met >= 70% korting**, en mailt
nieuwe treffers via Resend. `main` bevat alleen code; alle data staat op de branch `data`.

## Hoe het werkt

1. **Cloudflare Worker** (`worker/`) draait elke 5 minuten (cron `*/5 15-21 * * *`, UTC) en
   start alleen op de 61 scanmomenten van 17:30 t/m 22:30 Europe/Amsterdam (DST-correct).
2. De Worker start `.github/workflows/scan.yml` via `workflow_dispatch` met `scheduled_at`.
3. `python -m ah_scanner.cli scan` haalt **5 winkels** op, filtert categorie exact `Vlees`
   (niet `Vleeswaren`) met korting >= 70%, slaat het resultaat op en mailt nieuwe treffers.

| Winkel | ID |
| --- | --- |
| AH Blekersvaartweg | 1463 |
| AH Zandvoortselaan | 1348 |
| AH Casablancastraat | 1135 |
| AH Clothildestraat | 4046 |
| AH Westergracht | 8728 |

## Mail

Per scan met nieuwe treffers volgt **één HTML-mail** met een kaart per product: productfoto, korting,
prijs, winkel, voorraad, einde van de korting, **invriesbaar (Ja/Nee/Onbekend)** en de ruwe
bewaartekst ("Bewaren") van AH. Een product wordt per dag en winkel één keer gemeld (dedup).

- Foto en bewaartekst komen uit een aparte, best-effort GraphQL-aanroep per nieuw product
  (`src/ah_scanner/enrich.py`); een fout daarin laat scan en mail niet falen en wordt gelogd als
  `ENRICH_ERROR`. Resultaten staan gecachet in `product_info.json` op de `data`-branch.
- Invriesbaar wordt afgeleid met trefwoorden uit de bewaartekst; zinnen over *opnieuw* invriezen
  van ontdooid product tellen niet mee. De ruwe tekst blijft zichtbaar zodat je de regel kunt toetsen.

## Statussen

`OK`, `OK_ZERO_ROWS` (geldig), `INCOMPLETE` (een winkel viel uit) en `FAILED` (geen enkele winkel
of ongeldige auth). Alleen geldige scans tellen mee; een niet-geldige scan laat de workflow falen
(exitcode 4), een mailfout geeft exitcode 5.

Een late scan krijgt `late=true` en wordt opgeslagen met de **echte** starttijd naast het bedoelde
scanmoment; er wordt nooit teruggedateerd.

## Data (branch `data`)

- `scans/YYYY-MM-DD.jsonl`: een regel per scanmoment (idempotent per `scheduled_at`);
- `latest.json`: laatste scan; `notified.json`: dedup-state voor mails (laatste 7 dagen);
- `auth_state.enc`: geroteerde refresh-token, versleuteld met AES-256-GCM;
- `legacy/`: oude v1-data (jsonl, raw, days, central).

## Secrets en configuratie

| Waar | Naam | Doel |
| --- | --- | --- |
| GitHub Actions | `AH_REFRESH_TOKEN` | AH-sessie |
| GitHub Actions | `RESEND_API_KEY`, `AH_MAIL_FROM`, `AH_MAIL_TO` | mail via Resend |
| Cloudflare Worker | `GITHUB_TOKEN` | fine-grained, alleen *Actions: Read and write* |

Zie `.env.example`. Zonder eigen Resend-domein kan alleen naar het adres van het Resend-account
worden gestuurd (`onboarding@resend.dev`).

## Ontwikkelen

```bash
python -m pip install -e '.[dev]'
ruff check src tests/unit && ruff format --check src tests/unit
pytest --cov=ah_scanner --cov-fail-under=85
python -m unittest discover -s tests -p 'test_workflow_*.py'
cd worker && node --test
```

Handmatig testen: workflow **AH auth check** (alleen token) of **AH scan** met een geldig
`scheduled_at` (5-minutenslot binnen 17:30-22:30 Amsterdam).

CI (`ci.yml`, `engineering-quality.yml`) draait ruff, pytest, de workflow-contracttests en de
Worker-tests. Een wijziging aan `.github/workflows/` vereist een wijziging in
`tests/test_workflow_*.py`.
