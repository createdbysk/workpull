# Design 009 — Adopt

## Command

- `adopt <ticket>`
- Ticket id only, no state. Adopt goes to the first
  state, and priority has no relationship to state.

## Hook interface

- The adopt hook is an environment variable, not a
  CLI parameter: `ADOPT_HOOK` holds the command to
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
- The backend hook, on Workpull's instruction, assigns
  the ticket the state compatible with Workpull, the
  first state, and assigns its initial priority.
  Workpull does not compute the key, and does not
  assign the state itself.

## Adopt contract

- Priority is a Workpull concept, not a backend
  concept. Not all backend tickets will end up in
  Workpull, so the backend does not assign priority
  on creation. Workpull adopts a ticket first.
- The backend assigns a priority to a newly adopted
  ticket that would make it lower priority than
  every other ticket ever adopted into the system.
  Adoption order is priority order, until a
  prioritize move changes it.
- The first ticket adopted gets the first priority
  key. Each later ticket adopted gets a key after
  the last key, in adoption order, with no
  neighbours needed for the first ticket.

## Adopt result

- Hook exit 0 means adopted. The CLI exits 0 and prints
  the ticket id, and nothing else, for the Unix pipeline.
- Hook exit non-zero means not adopted. The CLI preserves
  that exit code, and prints no ticket id. That covers
  a ticket already in progress, a ticket already
  adopted, and a race, as a hook failure.
- A missing adopt hook means no adoption. The CLI exits
  2, and no adoption is invented.
- The CLI does not validate a ticket. The backend
  validates it, and rejects an in-progress ticket.

## What it does not do

- No create. Workpull does not create backend tickets.
- Workpull does not adopt a ticket already in progress.
  If Workpull adopts a ticket, it goes to the first
  state. The adopter should then move the ticket to
  the correct state, based on the capacity constraints.
- No move to the correct state. That advanced move is
  a future story, for later, not now.
- No prioritize. Adopt only assigns the initial
  priority, it does not move a ticket relative to
  others.
