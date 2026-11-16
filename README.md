# AH Laatste Kans scanner (v2)

Haalt dagelijks de AH Laatste Kans-aanbiedingen op, vooral **Vlees met >= 70% korting**, en mailt
nieuwe treffers via Resend. `main` bevat alleen code; alle data staat op de branch `data`.

## Hoe het werkt

1. **Cloudflare Worker** (`worker/`) draait elke 5 minuten (cron `*/5 15-21 * * *`, UTC) en
   start alleen op de 61 scanmomenten van 17:30 t/m 22:30 Europe/Amsterdam (DST-correct). Een
   tweede cron start om 22:45 Amsterdam de dagelijkse export (`export.yml`), een derde cron elke
   zondag om 23:15 Amsterdam het weekrapport (`report.yml`).
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

Een mail bevat **alle op dat moment geldende Vlees-aanbiedingen van 70% of meer, per filiaal**
(ook filialen zonder aanbod). Binnen een filiaal staat de aanbieding met de **hoogste voorraad
eerst** (bij gelijke voorraad op titel). Een nieuwe mail volgt zodra de stand verschilt van de vorige mail:
een aanbieding erbij of eraf. Een ongewijzigde stand geeft geen mail.

- Bovenaan staat wat er veranderd is (nieuw en verdwenen); nieuwe aanbiedingen hebben een label.
- Elke aanbieding is een kaart: productfoto, korting, prijs, voorraad, geldigheid (label
  **ALLEEN VANDAAG** bij einddatum vandaag, anders "Tot dd-mm-jjjj"),
  **invriesbaar (Ja/Nee/Onbekend)** en de ruwe bewaartekst ("Bewaren") van AH.
- Een aanbieding is uniek per winkel, product en einddatum van de korting. Elke dag begint zonder
  vorige stand (gisteren telt niet als "verdwenen").
- Valt een winkel uit in een scan, dan blijft de laatst bekende stand van die winkel staan (met een
  waarschuwing) en telt dat niet als "eraf". Zonder enige gelezen winkel volgt geen mail.
- De laatst verstuurde stand staat in `mail_state.json` op de `data`-branch; die wordt pas bijgewerkt
  na een geslaagde verzending, dus een mislukte mail wordt bij de volgende scan opnieuw geprobeerd.
- Foto en bewaartekst komen uit een aparte, best-effort GraphQL-aanroep per product
  (`src/ah_scanner/enrich.py`, gecachet in `product_info.json`); een fout daarin laat scan en mail
  niet falen en wordt gelogd als `ENRICH_ERROR`.
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
- `latest.json`: laatste scan; `mail_state.json`: laatst gemailde stand;
- `auth_state.enc`: geroteerde refresh-token, versleuteld met AES-256-GCM;
- `legacy/`: oude v1-data (jsonl, raw, days, central).

## Analyse

Alle scans staan op de `data`-branch: v2 in `scans/*.jsonl`, de oude v1-data in `legacy/`. Voor
analyse is er een tabel-export (CSV, UTF-8 met BOM zodat Excel hem goed opent):

- `analysis/scans/<dag>.csv`: een rij per scan en winkel (gelukt, aantallen, status, vertraging).
- `analysis/items/<dag>.csv`: een rij per scan, winkel en Vlees-aanbieding (alle percentages,
  `is_70` markeert >= 70%). Dezelfde kolommen voor v1 (`source=v1`) en v2 (`source=v2`).
- `canonical_5min` markeert scans op het 5-minutenraster (17:30, 17:35, ...). V1-scans liggen
  1 tot 3 minuten uit elkaar; filter hierop om v1 en v2 te vergelijken.
- Beperkingen: alleen de categorie Vlees; de vroegste v1-bestanden hebben geen producten
  (alleen of het ophalen lukte); er zit een gat van 4 t/m 14 november (storing).

Maken: de Worker start **AH export** elke avond om 22:45 Amsterdam automatisch (tweede cron
`45 20,21 * * *`, DST-correct gefilterd); je kunt de workflow ook handmatig draaien, of lokaal:

```bash
python -m ah_scanner.cli export --data-root <map-met-data-branch> --out analysis --combined
```

Inlezen in Python:

```python
import glob, pandas as pd
items = pd.concat(map(pd.read_csv, glob.glob("analysis/items/*.csv")))
```

## Weekrapport (trends)

`python -m ah_scanner.cli report --data-root <data-branch> --out reports [--mail]` (workflow
**AH report**) analyseert alle data (v1 en v2) en schrijft `reports/<jaar>-W<week>.md` naar de
`data`-branch; met `--mail` gaat het rapport ook per mail (zelfde afzender en adres als de scans).
De Worker start het elke zondag om 23:15 Amsterdam (cron `15 21,22 * * sun`, DST-correct gefilterd; Cloudflare telt weekdagen anders dan klassieke cron);
je kunt de workflow ook handmatig draaien.

Inhoud: trend (laatste 7 dagen tegenover de 7 dagen ervoor), op welk moment aanbiedingen naar 70%
gaan, en per filiaal, weekdag en week het aantal aanbiedingen, het aantal stuks en de aanbiedingen
die **geschikt zijn voor vier personen** (gewicht per pak maal voorraad >= 500 g, 125 g p.p.).

- Een aanbieding is een combinatie van dag, winkel, product en einddatum.
- Alleen **volledige dagen** (eerste scan uiterlijk 17:45, laatste scan vanaf 22:15) tellen mee voor
  gemiddelden en tijdstippen; onvolledige dagen vertekenen die cijfers. Groepen met minder dan 4 dagen
  zijn gemarkeerd. Er is geen verklaring in het rapport, alleen gemeten patronen.
- Aanbiedingen zonder gewicht in de data (bijvoorbeeld "per stuk") tellen niet mee voor vier personen.

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
