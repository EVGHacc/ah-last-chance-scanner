# Centrale AH Laatste Kans datastore

Dit is de centrale plek voor analyse van AH Laatste Kans-data.

## Structuur

- `raw/current/` — verwijzing naar de huidige authoritative dagbestanden in `data/YYYY-MM-DD.jsonl`.
- `raw/historical/` — gemigreerde snapshots uit `EVGHacc/FolderDeal/ah-last-chance/data`.
- `normalized/` — uniforme, afgeleide tabellen die verschillende meetregimes expliciet labelen.
- `derived/` — herleidbare analyses zoals eerste 70%-momenten en dagdekking.
- `metadata/` — bron-, schema- en meetregime-informatie.

## Bronnen

1. **Actuele productie**: `EVGHacc/ah-last-chance-scanner/data/YYYY-MM-DD.jsonl`.
2. **Historische bron**: `EVGHacc/FolderDeal/ah-last-chance/data`.

De actuele scannerrepository is voortaan de centrale analytische bron. De historische FolderDeal-data blijven als immutable provenance bestaan; centrale kopieën/normalisaties worden daaruit opgebouwd zonder de bron te wijzigen.

## Meetregimes

- `legacy-loose`: losse vroege scans, o.a. vanaf 2026-08-27.
- `official-1925`: vaste 19:25-momentopnamen.
- `legacy-observer`: fijnmaziger observerdata uit FolderDeal vóór de nieuwe scanner.
- `scanner-v5`: huidige 17:30–22:30 scanner met 101 raw 3-minutenpunten en 61 canonical 5-minutenpunten.

Vergelijk alleen metingen met een compatibel meetregime of label afwijkingen expliciet.
