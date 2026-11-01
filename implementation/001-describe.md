# Implementation 001 — Describe

## Language and tools

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: unittest, stdlib only, no pytest.
- Lint: pymarkdown, declared as a dev dependency in
  `pyproject.toml` (`pymarkdownlnt>=0.9.41`, install with
  `pip install -e ".[dev]"`).
- Project config: `pyproject.toml`, setuptools, Python 3.12.

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
  - `main(argv)`: runs the Click group. With no arguments,
    this is the real entry point. With arguments, the Click
    exit code is returned.
- `workpull/__main__.py`: entry point, `sys.exit(main())`.
- `workpull/__init__.py`: package marker.
- `adapters/mock_describe.py`: mock describe hook, prints the
  trivial Backlog/Done TOML view.
- `tests/test_describe.py`: tests, driving the CLI through
  Click's runner, with an explicit environment per test.

## Tests

Run: `python scripts/dev.py test`

Describe tests run through Click's runner, in an isolated
filesystem.

- Happy path: mock hook prints Backlog/Done, CLI exit 0, output
  parses as TOML with states Backlog and Done, claim Backlog -> Done.
- Missing hook: non-zero, no invented output.
- Failing hook: non-zero, no invented output.
- Invalid TOML output: non-zero.
- Transition to a state not in states: non-zero.
- Duplicate states, self-loop claim, backwards claim, and
  whitespace-padded state names: rejected, non-zero.
- Empty claim table: accepted, meaning every state is terminal.
- Hook command containing `;` and a side-effect command:
  side-effect not executed, with and without a space before `;`.
- State name containing shell metacharacters: rejected, non-zero.
- Hook output containing a TOML comment: comment is not printed,
  only the normalized view is printed.
- Spaced state name: claim keys are quoted in the normalized
  view, so the output re-parses as TOML.
- Unhashable state or claim target: rejected with a clean
  error, not a traceback.
- `--help` and `--version`: exit 0.

## Manual check

```bash
DESCRIBE_HOOK="python adapters/mock_describe.py" python -m workpull describe
```

Output:

```toml
states = ["Backlog", "Done"]

[claim]
"Backlog" = "Done"
```
