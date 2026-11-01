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
- `tests/test_click_cli.py`: CLI tests through Click's runner,
  in an isolated filesystem built with tempfile. A module-entry
  test proves `python -m workpull --help` still works.

## Tests

Run: `python scripts/dev.py test`

- Describe in an isolated filesystem: exit 0, TOML parses to
  Backlog and Done, claim Backlog -> Done.
- Isolated filesystem contains only the mock hook after the run.
- Missing hook: non-zero, no invented view.
- `--help` lists describe, exit 0.
- `--version` prints 0.1.0, exit 0.
- Unknown command: non-zero.
- Module entry: `python -m workpull --help` exit 0, lists describe.

## Manual check

```bash
python -m workpull --help
DESCRIBE_HOOK="python adapters/mock_describe.py" \
  python -m workpull describe
```
