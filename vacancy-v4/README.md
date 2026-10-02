# Vacancy Scanner v4 — clean sheet

v4 is an independent implementation.

## Hard boundary
- Coverage starts at 0.
- No code, adapters, snapshots, evidence, proof status or tests from vacancy-monitor/ or vacancy-v3/ may be imported.
- Legacy data may only be used once to construct a target source manifest containing organisation identity and first-party domains/seed URLs.
- Every source must be re-proven by v4 from live first-party evidence.

## Definition of verified_complete
A source is verified_complete only when its v4 provider adapter exhausts the official inventory and reconciles an authoritative total, or independently proves pagination exhaustion without unresolved duplicates/page-wrap/caps.

## Search and match location policy
- Candidate search, ranking and reporting focus on **Amsterdam**, **London**, and roles that are genuinely **fully remote**.
- Location filtering is a post-inventory matching concern only. It must never reduce provider discovery, authoritative inventory reconciliation, persisted job records, or `verified_complete` proof.
- Every verified source must therefore still persist its complete discovered inventory, including jobs outside the preferred locations.
- Hybrid or on-site roles outside Amsterdam/London are not treated as fully remote.
- Roles in other locations may be surfaced only when they are exceptionally interesting based on substantive fit and seniority; reports must explicitly label them as a location exception.
