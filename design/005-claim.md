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
- Actor identity is the hook's own operator context. Workpull
  does not invent an actor id. The backend hook knows its actor
  from its operator environment and backend credentials, and
  enforces the mutex on that basis.

## Claim ticket result

- The hook picks the ticket. The caller gives the state,
  not the ticket. The hook returns the ticket it claimed,
  as a single ticket id on stdout.
- Hook exit 0 means the mutex is acquired. The CLI exits 0
  and prints the ticket id returned by the hook, and nothing
  else.
- Hook exit non-zero means no ticket is claimed. The CLI
  preserves that exit code, and prints no ticket id.
- A missing claim ticket hook means no claim. The CLI exits 2,
  and no claim is invented.
- The CLI does not validate a state. It only
  forwards the hook's ticket id on success, and its exit
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
