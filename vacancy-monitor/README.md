# Vacancy Monitor 105

Public execution host for the vacancy-source scanner. It contains no credentials or personal data.

Every weekday the workflow checks the fixed registry of 105 recruiters/employers, classifies each source as official_site_scanned, official_ats_scanned, no_public_vacancy_board, or technical_failure, retries unresolved sources in a headless browser, and writes a complete daily JSON snapshot.

A run is accepted only when total_expected=105, total_classified=105 and complete=true. Technical failures remain explicitly visible rather than silently reducing scope.

`coverage_percent` measures registry classification, **not** recall of vacancies. `successful_control_percent` measures reachable sources. `vacancy_coverage_counts` is a separate conservative audit: `partial` means the scan observed individual job links but has not proved it read every page; `unproven` means no listing inventory was verified; `not_applicable_unverified` means the registry suggests there is no public client board but this has not been independently proved. `verified_complete` must remain zero until a source adapter compares the extracted inventory to an official count and traverses all pagination. No match recall percentage should be inferred from these counts. The direct live/apply check remains a further filter, not proof that discovery was complete.
