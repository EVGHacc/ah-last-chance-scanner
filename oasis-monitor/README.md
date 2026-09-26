# Oasis Live '27 Amsterdam — dagelijkse marktscan

Deze map bewaart de controleerbare historie van de ChatGPT-taak **Oasis doorverkoopmonitor Amsterdam** (dagelijks 21:00 Europe/Amsterdam). De taak doet live broncontroles. Dit is geen afzonderlijke GitHub Actions-runner; overige scanners en workflows worden niet gewijzigd.

## Scope
Evenementen: Johan Cruijff ArenA, 2027-07-16 en 2027-07-17, afzonderlijk. Primair 17 juli.
Vaste bronregister in `sources.json`; dynamische aanbieders mogen uitsluitend worden toegevoegd, niet als vervanging van vaste bronnen. Fanforums: r/oasis, relevante r/Tickets/r/concerts threads, Live4ever, Festivals United en relevante Nederlandse Oasis-discussies.

## Verplichte data
- `data/latest.json`: laatste *daadwerkelijk uitgevoerde* run, inclusief volledige bronstatus.
- `data/YYYY-MM-DD.json`: onveranderde dag-snapshot na succesvolle write/readback. Is er geen scan, dan **geen dag-snapshot verzinnen**.
- Elke bron per datum heeft een `status`: `verified_prices`, `verified_no_listings`, `blocked_or_login`, `technical_failure`, `not_listed`, `unverified`, met individuele `checkedAt`, `evidenceUrl`, `note`.
- Elke `listing`: `date`, `source`, `category`, `section` (optioneel), `askingPriceEur` per ticket of null, `allIn` true/false/null, `feeKnown` true/false, `listingCount` en `ticketCount` elk getal of null, `evidenceUrl`, `checkedAt`.
- `forumSignals`: bron, datum van bericht, URL, samenvatting, `type` ('firsthand', 'rumour', 'official_relay').
- `sourceCoverage`: geverifieerde bronnen en totale vaste bronnen per datum (tel een nul-aanbodpagina alleen als pagina live en nul expliciet bevestigd).
- Schrijf bedragen in euro's, geen gecachte prijzen als live of vraagprijzen als gerealiseerde verkopen. Aggregator-aanbiedingen niet dubbel bij voorraad optellen; nooit ontbrekende data met nul vullen.
- Na opslag bestand teruglezen en datum, 20 vaste bron/datum-combinaties, unieke source/date-paren, schema en individuele bewijslinks controleren. Rapporteer apart wanneer opslag faalt.

## Referentie
Officiële regels: https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27
Ticketprijzen: Front Standing €252,45; Rear Standing €201,96 (beide incl. servicekosten; verifieer categorie in actuele FAQ).
