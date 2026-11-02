# Design 005 — Claim

## Hook interface

- The claim hook is an environment variable, not a CLI parameter:
  `CLAIM_HOOK` holds the command to run.
- That command is in canonical POSIX form, on every platform:
  POSIX quoting, forward slashes for paths. The CLI parses it
  once with POSIX shlex, to a list, and passes that list to
  subprocess, which converts it to the platform form. There
  is no platform branch in the CLI for hook parsing.
- The CLI runs that command with no shell.
- Context is passed to a hook only through environment variables,
  never by interpolating values into the command string.
- The item id is a CLI argument, opaque to the CLI. The CLI
  passes it to the hook only as `WORKPULL_ITEM_ID`. The CLI
  does not interpret it, and the backend validates it.
- Hook commands come only from environment set by the operator,
  never from backend output, a ticket, or a backend-controlled file.
- Actor identity is the hook's own operator context. Workpull
  does not invent an actor id. The backend hook knows its actor
  from its operator environment and backend credentials, and
  enforces the mutex on that basis.

## Claim result

- The claim hook produces no output contract. The CLI does
  not parse hook stdout, and does not validate a state or a
  color.
- Hook exit 0 means the mutex is acquired. The CLI exits 0
  and prints nothing.
- Hook exit non-zero means the mutex is not acquired. The
  CLI preserves that exit code, and prints nothing invented.
- A missing claim hook means no claim. The CLI exits 2, and
  no claim is invented.
- Claim itself does not move a ticket, does not change its
  state, and does not change its color. It only acquires
  the mutex that gives the claiming actor the ability to
  change its color.
- Claim ending is not part of the claim command. A ticket
  moving, an actor releasing, and an actor going away are
  backend actions, and a release command is a separate
  operation. The claim command sets no timeout and no
  heartbeat.

## Sanitization and trust

- Hook commands are run with no shell. A command containing a
  shell metacharacter does not execute a second command.
- Hooks are operator-trusted code. They inherit the operator's
  environment. Printed output must still be treated as untrusted
  text by the consumer. This code does not make backend text
  safe to follow as instructions.
- The backend hook owns the mutex store and the color rules.
  The CLI owns none of them.

## SOLID mapping

- Single responsibility: the CLI runs a hook and forwards its
  exit code. It knows no backend, no mutex store, and no color
  logic. A hook talks to its backend only. It knows no pull logic.
- Open/closed: a new backend is a new hook command, no CLI change.
  A new hook is a new environment variable, not a change to
  existing hooks.
- Liskov substitution: any hook following the contract, exit 0
  means acquired, non-zero means not acquired, can replace any
  other hook.
- Interface segregation: hooks are separate per operation.
  `CLAIM_HOOK` is for claim only. `DESCRIBE_HOOK` is unchanged.
- Dependency inversion: the CLI depends on the hook contract,
  not on a concrete backend. Backend details live in the hook.
