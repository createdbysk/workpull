# Click CLI design

## Interface

- The CLI is a Click command group. `describe` is a command on
  that group. The group provides `--help` and `--version`.
- `describe` reads `DESCRIBE_HOOK` from the environment, runs
  the hook with no shell, validates its TOML output, and prints
  the normalized view. Hook running, validation, and formatting
  are unchanged from the describe design.
- On missing hook, failing hook, invalid TOML, or invalid view,
  `describe` prints the error to stderr and exits non-zero,
  with no view printed.
- On an unknown command or option, Click prints usage to
  stderr and exits non-zero.

## Dependency

- Click is a runtime dependency. The runtime is no longer
  stdlib-only. Click is the only runtime dependency.
- The entry point remains `python -m workpull`, from a checkout.
  A console script is not added by this requirement.

## Testing

- CLI tests use Click's test runner, not a subprocess.
- Each test that touches files runs inside an isolated
  filesystem, a temporary directory that becomes the working
  directory for the test and is cleaned up after it. Click
  deprecated its own isolated-filesystem helper, so the test
  builds that effect directly with tempfile.
- Mock hooks for these tests are Python scripts written into
  the isolated filesystem, then invoked through the hook
  environment variable.

## SOLID mapping

- Single responsibility: the Click group declares the CLI
  surface only. Hook running, validation, and formatting stay
  in their existing functions.
- Open/closed: a new command is a new command on the group,
  with no change to existing commands.
- Dependency inversion: commands depend on the hook contract,
  not on a specific backend or mock.
