# Vacancy Scanner v3

Outcome-first replacement for Vacancy Monitor v2.

## Invariants
- Registry scope is immutable during a run.
- Inventory discovery is separate from job-detail scraping and matching.
- Every source is independently classified; one source cannot fail the release of another.
- `verified_complete` requires a provider-specific completeness proof.
- Reachability, HTML link counts, matcher recall and technical scan status are never completeness proof.
- Previously verified sources are protected by golden regression evidence.

Architecture follows the monitor/scraper separation used by colophon-group/jobseek and small provider adapters used by ats-scrapers / ats-jobs-api-examples (MIT). No code copied yet.
