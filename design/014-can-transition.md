# Design 014 — Can Transition

## Command

- `can-transition <ticket> <to-state>`
- Ticket id and to-state, no from-state. Can transition
  checks whether the ticket can move to the to-state, so
  Workpull can decide before it moves a ticket. The
  backend provides the facts, Workpull decides.

## Hooks

- No new hook. Can transition uses the existing hooks:
  get-state (`GET_STATE_HOOK`, `WORKPULL_TICKET`) to get
  the ticket's current state, describe (`DESCRIBE_HOOK`)
  for transitions and WIP limits, and count
  (`COUNT_HOOK`, `WORKPULL_STATE` set to the to-state)
  for the to-state's wait count.
- Each hook is an environment variable, not a CLI
  parameter. Each command is in canonical POSIX form, on
  every platform: POSIX quoting, forward slashes for
  paths. The CLI parses it once with POSIX shlex, to a
  list, and passes that list to subprocess, which
  converts it to the platform form. There is no platform
  branch in the CLI for hook parsing.
- The CLI runs each command with no shell.
- Context is passed to a hook only through environment
  variables, never by interpolating values into the
  command string.

## Decision

- True only if both hold:
  - describe's transitions allow the ticket's current
    state to the to-state, and
  - the to-state's wait count is below its wait limit
    from describe. An `inf` wait limit always passes.
- Otherwise false. A current state or a to-state not in
  describe is false, not an error: the transition is
  not allowed from a state Workpull does not know, and
  a destination Workpull does not know has no limit to
  check against.

## Can-transition result

- The CLI exits 0 and prints `true` or `false`, and
  nothing else.
- It does not move, change state, change priority, or
  change a claim. It only reports whether the move is
  allowed.

## Failures

- A missing hook (`GET_STATE_HOOK`, `DESCRIBE_HOOK`,
  or `COUNT_HOOK`) means no decision. The CLI exits 2,
  and no answer is invented.
- A hook exit non-zero means no decision. The CLI
  preserves that exit code, and prints no answer.
- Invalid TOML from describe or count means no
  decision. The CLI exits 2, and prints no answer.
- Invalid describe output, under the describe contract,
  means no decision. The CLI exits 2, and prints no
  answer.
- An empty state from get-state means no decision. The
  CLI exits 2, and prints no answer.

## Implementation

- The existing `describe`, `get_state`, and `count`
  functions print and return `None`, so they cannot be
  composed. Can transition needs internal helpers that
  return values instead of printing: one that returns
  the ticket's current state, one that returns the
  validated describe view, and one that returns the
  to-state's wait count.
- Those helpers share the hook handling with the
  existing commands: missing hook is exit 2, a failing
  hook preserves its exit code, invalid TOML is exit 2.
- The existing commands keep their behaviour and their
  tests unchanged.

## What it does not do

- No move, no state change, no priority change, no
  claim change.
- There is no create command. Workpull does not create
  tickets.
