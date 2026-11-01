# Implementation 001 — Describe

## Language and tools

- Python 3.12, stdlib only for runtime, no runtime dependencies.
- Tests: unittest, stdlib only, no pytest.
- Lint: pymarkdown, declared as a dev dependency in
  `pyproject.toml` (`pymarkdownlnt>=0.9.41`, install with
  `pip install -e ".[dev]"`).
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

Run: `python scripts/dev.py test`

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

```bash
DESCRIBE_HOOK=adapters/mock_describe.sh python3 -m workpull describe
```

Output:

```toml
states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
```
