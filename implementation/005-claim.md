# Implementation 005 — Claim ticket

## Language and tools

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: unittest, stdlib only, no pytest.
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
    argument, prints the ticket id returned on stdout.
    Failing hook and empty ticket id are not handled yet. No
    code for them is written until a test requires it.
- `tests/test_claim_ticket.py`: tests, driving the CLI through
  Click's runner, with an explicit environment per test.
- `tests/test_workpull_cli.py`: top level help test, listing
  `claim-ticket` and `describe`.

## Tests

Run: `python scripts/dev.py test`

Claim ticket tests run through Click's runner, in an isolated
filesystem.

- Happy path: mock hook checks `WORKPULL_STATE` is `Develop`
  and prints `ticket-1`, CLI exit 0, output is `ticket-1`.
- `claim-ticket --help`: exit 0, shows `STATE` and
  "Claim a single ticket".
- Top level `--help`: exit 0, lists `claim-ticket` and
  `describe`, in `tests/test_workpull_cli.py`.

- Missing hook: no hook set, CLI exit 2, no ticket invented.

Failing hook and empty ticket id are not handled in the
code, and are not yet tested. To add either, write a red
test first, then the code that makes that test pass. No
defensive code without a test justifying it.
