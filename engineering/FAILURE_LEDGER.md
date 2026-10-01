# Failure Ledger

Use this ledger for failed production runs, rejected fixes and repeated provider
or protocol failures. Add one entry per materially distinct hypothesis.

| Date/UTC | Project | Source/component | Observed failure | Evidence/run | Root-cause hypothesis | Experiment/patch | Result | Next materially different hypothesis |
|---|---|---|---|---|---|---|---|---|

## Rules

- Record the observation before proposing the next fix.
- Link a commit, run, log or persisted evidence artifact whenever available.
- A repeated failed approach is allowed only when new evidence changes the
  hypothesis.
- Do not erase failed hypotheses after a later fix; they are regression
  knowledge.
- Production regressions remain open until the independent Production Verifier
  passes.
