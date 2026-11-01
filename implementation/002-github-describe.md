# Implementation 002 — GitHub issues describe

## Status

Implemented 2026-10-31. Tests passing, 2026-10-31.

## Concrete build

- Language: Python 3.12, stdlib only.
- Adapter: `plugins/github/describe.py`, run as
  `python plugins/github/describe.py` via `DESCRIBE_HOOK`.
  It prints exactly `states = ["Open", "Closed"]` and
  `[claim] Open = "Closed"`.
- No network call, no token, no issue listing in describe.
- CLI: unchanged from Requirement 001. `workpull describe`
  runs the hook, parses with `tomllib`, validates, and prints.
  Validation rejects any output that is not exactly states and
  claim, or whose claim source or target is not in states.

## Tests

- `tests/test_github_describe.py`, unittest, 2 tests:
  1. CLI via the GitHub adapter returns states Open, Closed
     and claim Open -> Closed.
  2. Adapter direct output is exactly states and claim, with
     no Backlog state leaking in from the mock model.
- Full suite after implementation: 9 tests, OK
  (7 from Requirement 001, 2 from this requirement).
- No live GitHub call is made in any test. The single trivial
  test issue for end-to-end testing is a later, manual step,
  not part of this requirement's automated tests.

## Out of scope

- Ready and claim for GitHub issues: later requirements.
- Label-based states: later requirement. This model is
  deliberately Open -> Closed only.
- Auth and token handling: not needed for describe, not added.
