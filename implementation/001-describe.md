# Implementation 001 — Describe

## Language and tools

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: pytest, plus Click's test runner for CLI tests.
- Lint: pymarkdown, declared as a dev dependency in
  `pyproject.toml` (`pymarkdownlnt>=0.9.41`, install with
  `pip install -e ".[dev]"`).
- Project config: `pyproject.toml`, setuptools, Python 3.12.

## Files

- `workpull/cli.py`
  - `run_hook(hook_command)`: parses the hook, in canonical
    POSIX form, with `shlex.split` in POSIX mode, runs the
    resulting list with `subprocess.run` and no shell, returns
    returncode, stdout, and stderr.
  - `validate_describe(view)`: checks the parsed TOML document
    against the design schema, returns an error string or None.
  - `describe(run_hook_fn)`: reads `DESCRIBE_HOOK`, runs the
    hook through the injected `run_hook_fn`, parses stdout
    with `tomllib`, validates, prints the view on success,
    returns a non-zero exit code on failure.
  - `cli()`: composition root. Wires the real `run_hook` into
    `ctx.obj`, unless a caller already supplied one, so tests
    can inject a fake. Thin Click commands call the
    implementations above with `ctx.obj["run_hook"]`.
- `workpull/__main__.py`: entry point, calls `cli()`. No
  programmatic path. Tests use Click's runner, with `runner`
  and `run_describe` injected as pytest fixtures.
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
  parses as TOML with states Backlog and Done, transition Backlog -> Done,
  and wip_limits Backlog work unlimited with wait 3, Done work
  and wait unlimited.
- Missing hook: non-zero, no invented output.
- Injected run hook: a fake `run_hook` supplied in `ctx.obj`
  is used instead of the real one, CLI exit 0 with the
  fake's view.
- Failing hook: non-zero, no invented output.
- Invalid TOML output: non-zero.
- Transition to a state not in states: non-zero.
- Duplicate states, self-loop transition, backwards transition, and
  whitespace-padded state names: rejected, non-zero.
- Empty transitions table: accepted, meaning every state is terminal.
- Hook command containing `;` and a side-effect command:
  side-effect not executed, with and without a space before `;`.
- State name containing shell metacharacters: rejected, non-zero.
- Hook output containing a TOML comment: comment is not printed,
  only the normalized view is printed.
- Spaced state name: transition keys are quoted in the normalized
  view, so the output re-parses as TOML.
- Unhashable state or transition target: rejected with a clean
  error, not a traceback.
- `--help` and `--version`: exit 0.

## Manual check

```bash
DESCRIBE_HOOK="python adapters/mock_describe.py" python -m workpull describe
```

Output:

```toml
states = ["Backlog", "Done"]

[transitions]
"Backlog" = "Done"

[wip_limits]
"Backlog" = {work = inf, wait = 3}
"Done" = {work = inf, wait = inf}
```
