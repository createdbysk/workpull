# Design 008 — Prioritize

## Command

- `prioritize <state> <ticket> --above <other-ticket>`
- `prioritize <state> <ticket> --below <other-ticket>`
- `prioritize <state> <ticket> --top`
- `prioritize <state> <ticket> --up`
- `prioritize <state> <ticket> --down`

One move at a time. The user never types a fractional
value. The move is relative, like a visual board drag.

## Hook interface

- The prioritize hook is an environment variable, not a
  CLI parameter: `PRIORITIZE_HOOK` holds the command to
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
  command string: `WORKPULL_STATE`, `WORKPULL_TICKET`,
  and one of `WORKPULL_ABOVE`, `WORKPULL_BELOW`,
  `WORKPULL_TOP`, `WORKPULL_UP`, or `WORKPULL_DOWN`.
- Hook commands come only from environment set by the
  operator, never from backend output, a ticket, or a
  backend-controlled file.
- The backend hook owns the fractional order keys. It
  computes the midpoint key between the neighbours,
  assigns it, and keeps values unique. The CLI does not
  know fractional indexing, and does not compute a key.

## Prioritize result

- Hook exit 0 means moved. The CLI exits 0 and prints
  the ticket id, and nothing else, for the Unix pipeline.
- Hook exit non-zero means not moved. The CLI preserves
  that exit code, and prints no ticket id. That is the
  race error, a conflict, low occurrence, error and retry.
- A missing prioritize hook means no move. The CLI exits
  2, and no move is invented.
- The CLI does not validate a state, a ticket, or a
  neighbour. The backend validates them.

## What it does not do

- No begin / end lock. No column claim. No bulk session
  in this command. A single move is atomic in the
  backend.
- Prioritization only changes priority. It does not move
  a ticket to another state, and it does not change its
  claim.
- There is no create command. Workpull does not create
  tickets.
