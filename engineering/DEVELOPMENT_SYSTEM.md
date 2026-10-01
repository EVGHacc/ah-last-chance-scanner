# Development System — AH & Vacancy Monitor

This repository uses an evidence-first development process for every functional
change. It applies to the AH Laatste Kans scanner, Vacancy Monitor v2, shared
scripts and GitHub Actions.

## Roles and responsibilities

### Builder
Owns one small change on a dedicated branch. The Builder may inspect, reproduce,
implement and run developer tests, but **may not declare the change production
ready**. A Builder must not weaken a test or verifier merely to make a change
pass.

### Test Author
Defines the failing reproducer and regression contract before, or together with,
the implementation. Functional AH changes require a dedicated `tests/test_ah_*.py`
change. Vacancy changes require `vacancy-monitor/test_*.py` or
`tests/test_vacancy_*.py`. Test changes must exercise the failure mode, not only
reachability or a happy path.

### Independent Reviewer
Runs in a separate read-only CI job after Builder tests. The reviewer checks the
diff, policy invariants, regression scope and cross-project impact. It has no
write permission and must not patch the code it reviews. A failed review returns
the work to the Builder.

### Production Verifier
Runs after a production workflow using only published evidence. It is read-only,
has no production secrets, and independently recomputes critical claims. A green
production workflow is **not** sufficient proof on its own.

### Release Controller
Allows merge/release only when policy, developer tests, independent review and
the applicable production/canary proof are green. The Release Controller never
converts `partial`, `unproven` or `technical_failure` into a success claim.

### SRE / Incident Owner
Owns production regressions. It records the observed failure, evidence, current
root-cause hypothesis and next materially different experiment. Repeating a
failed approach without new evidence or a new hypothesis is prohibited.

## Mandatory development loop

1. **Inspect current production first.** Read current code, evidence and recent
   Actions output before editing.
2. **Research before implementation.** For provider/protocol/browser failures,
   inspect first-party behaviour and proven public implementations before
   choosing a fix.
3. **Reproduce.** Add a deterministic failing test or fixture for the observed
   bug wherever practical.
4. **Implement one micro-task.** Keep the patch small and attributable.
5. **Builder tests.** Compile/lint as applicable and run the project test suite.
6. **Independent review.** A separate read-only job reviews policy and
   regressions; it cannot modify source.
7. **Canary / production verification.** Recompute claims from published
   evidence rather than trusting the workflow exit code.
8. **Release or return.** Any failed gate returns to the Builder with evidence.
9. **Persist learning.** Record failed hypotheses and production regressions in
   the failure ledger.

## Independence rules

- Independent Reviewer and Production Verifier run as separate CI jobs.
- Both use `contents: read` and receive no production secrets.
- Production data writers are not production verifiers.
- Generated snapshots are never committed in the same change as functional
  source/workflow code.
- A code author cannot satisfy a missing test by weakening the verifier.
- Historical vacancy IDs may not be treated as permanently live fixtures.

## Project-specific proof

### AH Laatste Kans scanner

Developer proof:
- compile production scripts;
- run `scripts/selftest.py`, schedule/session self-tests and authentication-state
  tests;
- add/update a dedicated root `tests/test_ah_*.py` regression for functional
  changes.

Independent production proof:
- `scripts/independent_qa.py` rescans the published JSONL archive;
- validates user-refresh authentication, five-store scope, Vlees scope, timing,
  raw/canonical cadence and status/archive consistency;
- at end-of-session, all expected slots must be independently present.

### Vacancy Monitor v2

Developer proof:
- provider/unit/regression tests;
- registry integrity;
- adapter-specific malformed/duplicate/pagination tests;
- no source may become `verified_complete` from reachability alone.

Independent production proof:
- registry size is derived dynamically from `registry.tsv`;
- snapshot identities must exactly equal registry identities;
- `verified_complete` requires persisted exhaustive inventory evidence;
- if an official total exists, observed inventory must equal it;
- live jobs must independently satisfy detail-live + current-board + HTTP 200 +
  apply-live;
- technical-failure and coverage aggregates are recomputed from organisations.

For Workday, Recruitee, Greenhouse, Lever, SmartRecruiters and Ashby, existing
provider-specific strictness remains mandatory. Organisation-specific priority
work follows the user's selected priorities.

## Definition of Done

A functional change is Done only when all applicable items are true:

- root cause or feature contract documented;
- regression test added or updated;
- developer tests green;
- independent read-only review green;
- no unrelated generated evidence mixed into the source change;
- canary/production evidence green where the change affects live behaviour;
- no unresolved count, pagination, identity or snapshot/registry mismatch;
- failure ledger updated when a failed hypothesis or production regression was
  involved;
- commit/run evidence is traceable.

Anything less is **implemented or tested**, not **production verified**.
