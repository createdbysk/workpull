# Design 011 — Transition

## Command

- `transition <ticket> <to-state> <token>`
- Ticket id, to-state, and token, no from-state. Transitions go
  from a state to a state. Transition moves the ticket
  into the wait state for the to-state. Claim ends on
  the move. The token is the one the backend issued when
  the ticket was claimed. See design 015.

## Check first

- Transition first checks, Workpull side, using the
  can-transition decision: get-state (`GET_STATE_HOOK`,
  `WORKPULL_TICKET`) to get the ticket's current state,
  describe (`DESCRIBE_HOOK`) for transitions and WIP
  limits, and count (`COUNT_HOOK`, `WORKPULL_STATE` set
  to the to-state) for the to-state's wait count.
- The check is true only if describe's transitions allow
  the ticket's current state to the to-state, and the
  to-state's wait count is below its wait limit from
  describe. An `inf` wait limit always passes. A current
  state or a to-state not in describe is false.
- Only if the check is true does transition call the
  transition hook to move the ticket.
- If the check is false, no move happens, the transition
  hook is not called, the CLI exits 2, and prints no
  ticket id.
- If any check hook is missing, failing, or returns
  invalid TOML, describe, or count output, the check has
  no decision: a missing hook is exit 2, a failing hook
  preserves its exit code, invalid output is exit 2, and
  no move happens.

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
  command string: `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`, and `WORKPULL_TOKEN`.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the move. It validates the token
  against the claim on the ticket, and moves only if it
  matches. Workpull does not check the token itself.

## Transition result

- Hook exit 0 means transitioned. The CLI exits 0 and prints
  the ticket id, and nothing else, for the Unix pipeline.
- Hook exit non-zero means not transitioned. The CLI preserves
  that exit code, and prints no ticket id. That covers a
  wrong token and a race, as a hook failure.
- Hook exit 0 with empty stdout means not transitioned. Exit
  0 means transitioned with one ticket id, so a hook that
  exits 0 and prints nothing breaks that contract. The
  CLI exits 2, and prints no ticket id.
- A missing transition hook means no transition. The CLI exits
  2, and no transition is invented.
- The CLI does not validate a ticket or a to-state. Workpull
  validates the move with the can-transition check, using
  get-state, describe, and count.

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
