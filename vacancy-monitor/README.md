# Vacancy Monitor 99

Public execution host for the vacancy-source scanner. It contains no credentials or personal data.

Every weekday the workflow checks the fixed registry of 99 recruiters/employers, classifies each source as official_site_scanned, official_ats_scanned, no_public_vacancy_board, or technical_failure, retries unresolved sources in a headless browser, and writes a complete daily JSON snapshot.

A run is accepted only when total_expected=99, total_classified=99 and complete=true. Technical failures remain explicitly visible rather than silently reducing scope.
