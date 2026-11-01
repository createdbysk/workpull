# Implementation 002 — GitHub issues describe

## Concrete build

- Language: Python 3.12, stdlib only.
- Adapter: `plugins/github/describe.py`, run as
  `python plugins/github/describe.py` via `DESCRIBE_HOOK`.
  It prints exactly `states = ["Open", "Closed"]` and
  `[claim] Open = "Closed"`.
- No network call, no token, no issue listing in describe.
- CLI: unchanged. `workpull describe`
  runs the hook, parses with `tomllib`, validates, and prints.
  Validation rejects any output that is not exactly states and
  claim, or whose claim source or target is not in states.

## Tests

- `tests/test_github_describe.py`, unittest, 2 tests:
  1. CLI via the GitHub adapter returns states Open, Closed
     and claim Open -> Closed.
  2. Adapter direct output is exactly states and claim, with
     no Backlog state in it.
- No live GitHub call is made in any test.

## Out of scope

- Ready and claim for GitHub issues.
- Label-based states. This model is Open -> Closed only.
- Auth and token handling: not needed for describe, not added.
