# Design 011 — Transition

## Command

- `transition <ticket> <to-state>`
- Ticket id and to-state, no from-state. Transitions go
  from a state to a state. Transition moves the ticket
  into the wait state for the to-state. Claim ends on
  the move.

## Hook interface

- The transition hook is an environment variable, not a
  CLI parameter: `TRANSITION_HOOK` holds the command to
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
  command string: `WORKPULL_TICKET` and
  `WORKPULL_TO_STATE`.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the move. It validates the
  transition, and errors if the to-state is unreachable
  from the ticket's current state. The CLI does not know
  the ticket's current state, and does not validate the
  transition itself.

## Transition result

- Hook exit 0 means transitioned. The CLI exits 0 and prints
  the ticket id, and nothing else, for the Unix pipeline.
- Hook exit non-zero means not transitioned. The CLI preserves
  that exit code, and prints no ticket id. That covers a
  to-state unreachable from the ticket's current state,
  and a race, as a hook failure.
- Hook exit 0 with empty stdout means not transitioned. Exit
  0 means transitioned with one ticket id, so a hook that
  exits 0 and prints nothing breaks that contract. The
  CLI exits 2, and prints no ticket id.
- A missing transition hook means no transition. The CLI exits
  2, and no transition is invented.
- The CLI does not validate a ticket or a to-state. The backend
  validates them.

## What it does not do

- No begin / end lock. No priority change. Transition only
  moves the ticket into the wait state for the to-state,
  and ends the claim on the move. The ticket keeps its
  priority, counting against the wait state's WIP limit,
  unclaimed, so the system can move it on when the
  to-state has capacity.
- The system move from the wait state into the to-state
  is not this command. That is a later event.
- There is no create command. Workpull does not create
  tickets.
