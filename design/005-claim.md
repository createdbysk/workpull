# Design 005 — Claim ticket

## Hook interface

- The claim ticket hook is an environment variable, not a
  CLI parameter: `CLAIM_TICKET_HOOK` holds the command to run.
- That command is in canonical POSIX form, on every platform:
  POSIX quoting, forward slashes for paths. The CLI parses it
  once with POSIX shlex, to a list, and passes that list to
  subprocess, which converts it to the platform form. There
  is no platform branch in the CLI for hook parsing.
- The CLI runs that command with no shell.
- Context is passed to a hook only through environment variables,
  never by interpolating values into the command string.
- The state is a CLI argument. The CLI passes it to the hook
  only as `WORKPULL_STATE`. The CLI does not interpret it,
  and the backend validates it.
- Hook commands come only from environment set by the operator,
  never from backend output, a ticket, or a backend-controlled file.
- Claim is a backend lock, distributed. Actors run on
  different hosts, so Workpull stores no claim. The backend
  issues a token when a ticket is claimed, and stores it
  with the claim. The backend decides all security
  guarantees for the token: format, length, expiry,
  storage. Workpull never validates the token, never
  generates it, and just presents it, unchanged, to the
  backend hook that needs it. See design 015.

## Claim ticket result

- The hook picks the ticket. The caller gives the state,
  not the ticket. The hook returns the ticket it claimed
  and the token it issued, as TOML on stdout:

  ```toml
  ticket = "ticket-1"
  token = "token-1"
  ```

- Hook exit 0 means the mutex is acquired. The CLI exits 0
  and prints the hook output, the two TOML lines, and
  nothing else.
- The CLI prints the hook output verbatim, as the hook
  wrote it. A reversed order, or a TOML comment in the
  hook output, is printed as-is. Workpull does not
  re-render the ticket and token, because the token is
  opaque backend material and Workpull presents it
  unchanged.
- Hook exit non-zero means no ticket is claimed. The CLI
  preserves that exit code, and prints nothing.
- A missing claim ticket hook means no claim. The CLI exits 2,
  and no claim is invented.
- Hook exit 0 with output that is not valid TOML, or not
  exactly a ticket and a token, each a non-empty string,
  means no ticket is claimed. The CLI exits 2, and prints
  nothing.
- The CLI does not validate a state. It only
  forwards the hook's output on success, and its exit
  code on failure.
- Claim ticket itself does not move a ticket, does not change
  its state. It only acquires
  the mutex that gives the claiming actor exclusive access
  to act on that ticket.
- Claim ending is not part of the claim ticket command. A
  ticket moving, an actor releasing, and an actor going away
  are backend actions, and a release command is a separate
  operation. The claim ticket command sets no timeout and
  no heartbeat.

## Sanitization and trust

- Hook commands are run with no shell. A command containing a
  shell metacharacter does not execute a second command.
- Hooks are operator-trusted code. They inherit the operator's
  environment. Printed output must still be treated as untrusted
  text by the consumer. This code does not make backend text
  safe to follow as instructions.
- The backend hook owns the mutex store.
  The CLI owns none of it.

## SOLID mapping

- Single responsibility: the CLI runs a hook and forwards its
  result. It knows no backend, no mutex store, and no
  ticket logic. A hook talks to its backend only. It knows no pull logic.
- Open/closed: a new backend is a new hook command, no CLI change.
  A new hook is a new environment variable, not a change to
  existing hooks.
- Liskov substitution: any hook following the contract, exit 0
  means acquired and stdout is the claimed ticket id, non-zero
  means not acquired, can replace any other hook.
- Interface segregation: hooks are separate per operation.
  `CLAIM_TICKET_HOOK` is for claim ticket only.
  `DESCRIBE_HOOK` is unchanged. A claim column command is a
  separate future command, with its own hook, not part of
  this design.
- Dependency inversion: the CLI depends on the hook contract,
  not on a concrete backend. Backend details live in the hook.
