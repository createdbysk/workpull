# Click CLI implementation

## Stack

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: unittest, stdlib only, no pytest, plus Click's test
  runner for CLI tests.

## Files

- `workpull/cli.py`: Click group `cli`, with `--version`,
  and a `describe` command. Hook running, validation, and
  formatting are unchanged. Errors print to stderr and exit
  non-zero, with no view printed.
- `workpull/__main__.py`: unchanged, entry point is `main()`,
  which runs the Click group.
- `pyproject.toml`: runtime dependency `click>=8.1,<9`.
- `scripts/dev.py`: test command uses the venv Python when a
  venv exists, so the Click dependency is available, else the
  system Python.
- `tests/test_describe.py`: describe tests through Click's
  runner, in an isolated filesystem built with tempfile,
  including the help test for describe and the version test.
  There is no separate Click test file: Click is a framework,
  not a capability, and unknown commands are not tested,
  because Click's default handling is assumed correct. The
  module entry is not tested: Python and Click are assumed
  correct.

## Tests

Run: `python scripts/dev.py test`

- Describe in an isolated filesystem: exit 0, TOML parses to
  Backlog and Done, claim Backlog -> Done.
- `--help` lists describe, exit 0.
- `--version` prints 0.1.0, exit 0.

## Manual check

```bash
DESCRIBE_HOOK="python adapters/mock_describe.py" \
  python -m workpull describe
```
