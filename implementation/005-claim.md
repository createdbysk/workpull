# Implementation 005 — Claim ticket

## Language and tools

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: pytest, plus Click's test runner for CLI tests.
- Lint: pymarkdown, declared as a dev dependency in
  `pyproject.toml` (`pymarkdownlnt>=0.9.41`, install with
  `pip install -e ".[dev]"`).
- Project config: `pyproject.toml`, setuptools, Python 3.12.

## Files

- `workpull/cli.py`
  - `run_hook(hook_command, env=None)`: parses the hook, in
    canonical POSIX form, with `shlex.split` in POSIX mode,
    runs the resulting list with `subprocess.run` and no shell,
    returns returncode, stdout, and stderr. `env`, when given,
    is merged over the process environment for the hook only.
    Describe calls it with no extra env.
  - `claim_ticket(state)`: reads `CLAIM_TICKET_HOOK`, returns
    exit 2 with no ticket invented when the hook is missing,
    runs the hook with `WORKPULL_STATE` set to the state
    argument, preserves the hook's exit code on failure,
    returns exit 2 with no ticket invented when the hook
    exits 0 but returns an empty ticket id, prints the
    ticket id returned on stdout on success.
- `tests/test_claim_ticket.py`: tests, driving the CLI through
  Click's runner, with an explicit environment per test.
- `tests/test_workpull_cli.py`: top level help test, listing
  `claim-ticket` and `describe`.

## Tests

Run: `python scripts/dev.py test`

Claim ticket tests run through Click's runner, in an isolated
filesystem.

- Happy path, parametrized with `pytest.mark.parametrize`: mock hook
  checks `WORKPULL_STATE` is `Develop` and prints the ticket
  id, CLI exit 0, output is that id. Cases: `ticket-1`
  and `0`. The `0` case proves a ticket id of `0`, a
  non-empty string, is not treated as empty.
- `claim-ticket --help`: exit 0, shows `STATE` and
  "Claim a single ticket".
- Top level `--help`: exit 0, lists `claim-ticket` and
  `describe`, in `tests/test_workpull_cli.py`.

- Missing hook: no hook set, CLI exit 2, no ticket invented.

- Failing hook: hook exits 3, CLI exit 3, no ticket invented.
- Empty ticket id: hook exits 0 but returns no ticket id,
  CLI exit 2, no ticket invented.
