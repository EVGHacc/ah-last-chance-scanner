# Vacancy Scanner v4 — clean sheet

v4 is an independent implementation.

## Hard boundary
- Coverage starts at 0.
- No code, adapters, snapshots, evidence, proof status or tests from vacancy-monitor/ or vacancy-v3/ may be imported.
- Legacy data may only be used once to construct a target source manifest containing organisation identity and first-party domains/seed URLs.
- Every source must be re-proven by v4 from live first-party evidence.

## Definition of verified_complete
A source is verified_complete only when its v4 provider adapter exhausts the official inventory and reconciles an authoritative total, or independently proves pagination exhaustion without unresolved duplicates/page-wrap/caps.
