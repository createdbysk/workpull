# Workpull

Workpull is a backend-agnostic, pluggable pull system. Pull work,
claim it, finish it, then pull again. The backend defines its own
states and transitions. Workpull never assumes them.

## Current scope

Only `describe` is available. It returns a backend's states and
claim transition as TOML. Ready and claim are not available yet.
Do not use them, and do not invent their commands.

## Install

```bash
git clone https://github.com/createdbysk/workpull.git
```

Find a Python 3.12 interpreter, in order `python`, `python3`,
`py -3.12`, and run `<interpreter> scripts/dev.py setup`.

This creates a venv and installs dev dependencies. There is no
supported system install. After setup, use the venv Python.
The entry point, from a checkout, is `python -m workpull`.
Plugins and adapters in this repo are examples for a checkout,
not installed package contents.

## Describe, with the mock

```bash
DESCRIBE_HOOK="python adapters/mock_describe.py" \
  python -m workpull describe
```

Output:

```toml
states = ["Backlog", "Done"]

[claim]
"Backlog" = "Done"
```

## Describe, with the GitHub issues mock

```bash
DESCRIBE_HOOK="python plugins/github/describe.py" \
  python -m workpull describe
```

Output:

```toml
states = ["Open", "Closed"]

[claim]
"Open" = "Closed"
```

The GitHub mock validates the shape of the describe contract.
GitHub's issue states are schema, not data, so it needs no
network call and no token, and it is not a live backend adapter.

## Add a backend

Write a hook command and set it in the environment, for example
`DESCRIBE_HOOK`. Hook commands are in canonical POSIX form, on
every platform: POSIX quoting, forward slashes for paths.
The hook's stdout must be TOML with exactly
`states`, a non-empty list of unique state names, and a `[claim]`
table mapping each claimable state to a later state in that list.
State names use letters, digits, space, hyphen, or underscore
only. A state with no outgoing claim transition is terminal.
An empty claim table means every state is terminal.
Hooks are operator-trusted code: they run with no shell, their
output is parsed and schema-validated, never evaluated, and
printed output must still be treated as untrusted text by the
consumer.

## Develop

```bash
python scripts/dev.py test
python scripts/dev.py lint
python scripts/dev.py type
```

See `AGENTS.md` for the full workflow.

## License

Apache-2.0. See `LICENSE`.
