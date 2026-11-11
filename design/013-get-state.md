# Design 013 — Get State

## Command

- `get-state <ticket>`
- Ticket id only, no state. Get state returns the
  ticket's current state, so Workpull can check whether
  a destination state is reachable from it. The backend
  provides the state, Workpull decides.

## Hook interface

- The get-state hook is an environment variable, not a
  CLI parameter: `GET_STATE_HOOK` holds the command to
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
  command string: `WORKPULL_TICKET` only.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the ticket's current state.
  The CLI does not know the ticket's current state,
  and does not ask for it any other way.

## Get-state result

- Hook exit 0 means found. The CLI exits 0 and prints
  the state name, and nothing else.
- A ticket in wait is in the state it waits for, not
  the work state it left, because that is where the
  ticket is now. Get state returns the waiting-for
  state for a waiting ticket.
- Hook exit non-zero means not found. The CLI preserves
  that exit code, and prints no state name.
- Hook exit 0 with empty stdout means not found. Exit
  0 means found with one state name, so a hook that
  exits 0 and prints nothing breaks that contract. The
  CLI exits 2, and prints no state name.
- A missing get-state hook means no state. The CLI exits
  2, and no state is invented.
- The CLI does not validate a ticket or a state. The
  backend validates them.

## What it does not do

- No move, no state change, no priority change, no
  claim change. Get state only reports the ticket's
  current state.
- There is no create command. Workpull does not create
  tickets.
