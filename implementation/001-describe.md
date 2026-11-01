# Implementation 001 — Describe

This document states the concrete build for requirement 001.
See `requirements/001-describe.md` for what is required, and
`design/001-describe.md` for how it is designed.

## Language and tools

- Python 3.12, stdlib only, no dependencies.
- Tests: unittest, stdlib only, no pytest.
- Project config: `pyproject.toml`, setuptools, Python >= 3.12.

## Files

- `workpull/cli.py`
  - `run_hook(hook_command)`: parses the hook with `shlex.split`,
    runs it with `subprocess.run` and no shell, returns returncode,
    stdout, and stderr.
  - `validate_describe(view)`: checks the parsed TOML document
    against the design schema, returns an error string or None.
  - `describe()`: reads `DESCRIBE_HOOK`, runs the hook, parses
    stdout with `tomllib`, validates, prints the view on success,
    returns a non-zero exit code on failure.
  - `main(argv)`: dispatches `["describe"]`, usage error otherwise.
- `workpull/__main__.py`: entry point, `sys.exit(main())`.
- `workpull/__init__.py`: package marker.
- `adapters/mock_describe.sh`: mock describe hook, prints the
  trivial Backlog/Done TOML view.
- `tests/test_describe.py`: tests, driving the CLI as a subprocess
  with an explicit environment per test.

## Tests

Run: `python3 -m unittest tests.test_describe -v`

7 tests, all passing 2026-10-31:

- Happy path: mock hook prints Backlog/Done, CLI exit 0, output
  parses as TOML with states Backlog and Done, claim Backlog -> Done.
- Missing hook: non-zero, no invented output.
- Failing hook: non-zero, no invented output.
- Invalid TOML output: non-zero.
- Transition to a state not in states: non-zero.
- Hook command containing `;` and a side-effect command:
  side-effect not executed, non-zero.
- State name containing shell metacharacters: rejected, non-zero.

## Manual check

```
DESCRIBE_HOOK=adapters/mock_describe.sh python3 -m workpull describe
```

Output:

```
states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
```
