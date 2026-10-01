## Change contract

**Project**
- [ ] AH Laatste Kans scanner
- [ ] Vacancy Monitor v2
- [ ] Shared engineering / CI

**Role separation**
- Builder:
- Test Author:
- Independent Reviewer: CI read-only gate
- Production Verifier: post-production read-only gate

## Problem / root cause

Describe the observed failure or feature contract and link the production evidence,
run or reproducible fixture.

## Research used

For protocol/provider/browser changes, list first-party behaviour and the proven
implementation/documentation pattern that informed the fix.

## Reproducer

Describe the failing test or fixture added before/together with the change.

## Implementation

List exact files/functions changed and why the patch is minimal.

## Evidence

- [ ] Dedicated regression test added/updated
- [ ] Developer tests green
- [ ] Independent review green
- [ ] No generated production snapshots mixed with source changes
- [ ] Canary/production proof green when live behaviour changed
- [ ] Failure ledger updated for failed hypothesis/production regression

## Production proof

Record the production workflow/run and independent verifier result. Do not mark a
source or scan fixed from reachability or a green writer workflow alone.
