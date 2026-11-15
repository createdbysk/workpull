# Click CLI

## Intent

The CLI is declared, not inferred. Commands, help, version, and
errors are an explicit surface, stable as commands are added.

## What

- The CLI provides a command group with a `describe` command.
- `describe` behaves as before: it runs the describe hook and
  returns the validated, normalized generic view, or fails with
  no invented view.
- `--help` lists available commands and their purpose.
- `--version` prints the version.
- An unknown command or option fails with usage and a non-zero
  exit, not a silent success.
- Tests for the CLI run in an isolated filesystem, so a mock
  adapter that reads or writes files cannot pollute the repo,
  and its files are cleaned up after the test.

## Out of scope

Ready and claim are not available. Their commands are not added
by this requirement.
