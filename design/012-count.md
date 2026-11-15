# Design 012 — Count

## Command

- `count <state>`
- State only. Count returns how many tickets are in a
  state, so Workpull can make the WIP decision. The
  backend provides the count, Workpull decides.

## Hook interface

- The count hook is an environment variable, not a
  CLI parameter: `COUNT_HOOK` holds the command to
  run.
- That command is in canonical POSIX form, on every
  platform: POSIX quoting, forward slashes for paths.
  The CLI parses it once with POSIX shlex, to a list,
  and passes that list to subprocess, which converts it
  to the platform form. There is no platform branch in
  the CLI for hook parsing.
- The CLI runs that command with no shell.
- Context is passed to a hook only through environment
  variables, never by interpolating values into the
  command string: `WORKPULL_STATE` only.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the count. The CLI does not
  know how many tickets are in a state, and does not
  count them itself.

## Count result

- The hook returns TOML, similar to describe, so it
  can get richer later:

  ```toml
  wait = 2
  work = 3
  ```

  `wait` is the number of tickets in that state's
  wait state, `work` is the number of tickets in the
  state itself. Work counts tickets whose work state
  is that state, including a ticket in wait that left
  it, so a waiting ticket counts as work in the state
  it left and as wait in the state it waits for.
- Hook exit 0 means counted. The CLI exits 0 and prints
  the hook output, the two TOML lines, and nothing else.
- Hook exit 0 with output that is not valid TOML means
  not counted. The CLI exits 2, and prints no output.
- Hook exit 0 with output that is not exactly `wait`
  and `work`, each a non-negative integer, means not
  counted. The CLI exits 2, and prints no output. This
  is the same shape the can-transition helper checks,
  through the shared validator.
- The CLI does not validate a state. The backend
  validates it.

## What it does not do

- Count does not make the WIP decision, and does not
  move any ticket. It only reports the counts, so
  Workpull can decide.
- There is no create command. Workpull does not create
  tickets.
