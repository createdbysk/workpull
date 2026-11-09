# Design 010 — Release

## Command

- `release <ticket>`
- Ticket id only, no state. Release ends the claim on a
  ticket, in the same column, in the same state.

## Hook interface

- The release hook is an environment variable, not a
  CLI parameter: `RELEASE_HOOK` holds the command to
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
- The backend hook owns the claim store. It ends the
  claim on the ticket. The CLI does not know the claim
  store, and does not end the claim itself.

## Release result

- Hook exit 0 means released. The CLI exits 0 and prints
  the ticket id, and nothing else, for the Unix pipeline.
- Hook exit non-zero means not released. The CLI preserves
  that exit code, and prints no ticket id. That covers a
  ticket with no claim to release, and a race, as a hook
  failure.
- Hook exit 0 with empty stdout means not released. Exit
  0 means released with one ticket id, so a hook that
  exits 0 and prints nothing breaks that contract. The
  CLI exits 2, and prints no ticket id.
- A missing release hook means no release. The CLI exits
  2, and no release is invented.
- The CLI does not validate a ticket. The backend
  validates it.

## What it does not do

- No begin / end lock. No state change. No priority
  change. Release only ends the claim. The ticket stays
  in the same state, with the same priority, counting
  against the same WIP limit, unclaimed, so someone
  else can claim it again.
- There is no create command. Workpull does not create
  tickets.
