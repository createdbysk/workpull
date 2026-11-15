# Design 018 — Discard

## Command

- `discard <ticket> <token>`
- Ticket id and token, no state. Discard is a
  claim-holder operation: only a ticket with a claim can
  be discarded, and only by the actor holding the claim.
  The token is the one the backend issued when the ticket
  was claimed. See design 015.
- A claim initiates a conversation: it names the
  accountable holder of the ticket. Discard belongs to
  the holder, so anyone else who wants the ticket
  discarded talks to the holder. There is no unilateral
  discard of a claimed ticket.

## Hook interface

- The discard hook is an environment variable, not a
  CLI parameter: `DISCARD_HOOK` holds the command to
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
  command string: `WORKPULL_TICKET` and `WORKPULL_TOKEN`.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the claim store. It validates
  the token against the claim on the ticket, and
  discards only if it matches. The CLI does not know
  the claim store, does not validate the token, and
  does not discard the ticket itself.

## Discard result

- Hook exit 0 means discarded. The CLI exits 0 and
  prints the ticket id, and nothing else, for the Unix
  pipeline.
- A discard takes the ticket out of the system: it is
  in no state, carries no priority, and counts against
  no state's WIP. The claim ends, and the token is
  invalid afterwards: the backend no longer honors it.
- Hook exit non-zero means not discarded. The CLI
  preserves that exit code, and prints no ticket id.
  That covers a wrong token, a ticket with no claim to
  discard, and a race, as a hook failure.
- Hook exit 0 with empty stdout means not discarded.
  Exit 0 means discarded with one ticket id, so a hook
  that exits 0 and prints nothing breaks that contract.
  The CLI exits 2, and prints no ticket id.
- A missing discard hook means no discard. The CLI
  exits 2, and no discard is invented.
- The CLI does not validate a ticket. The backend
  validates it.

## What it does not do

- No cascade. Discard opens the ticket's WIP, and the
  CLI performs no other state change: it does not pull
  a waiting ticket into the opened slot, and it does
  not move any other ticket.
- No begin / end lock. The discard itself is the one
  backend operation, through the hook.
- Discard is final from Workpull's standpoint. No
  Workpull command brings a discarded ticket back.
