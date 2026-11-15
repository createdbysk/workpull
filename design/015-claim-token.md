# Design 015 — Claim token

## Claim

- Claim is a backend lock, distributed. Actors run on
  different hosts, so a local claim store in Workpull
  cannot work. The backend owns the claim store.
- The backend issues the token when a ticket is claimed,
  and stores it with the claim. The backend decides all
  security guarantees for the token: format, length,
  expiry, storage. Workpull never validates the token,
  never generates it, and never decides what makes a
  token good.
- Workpull just presents the token, unchanged, to the
  backend hook that needs it.

## Claim ticket

- `claim-ticket <state>`
- The backend hook picks the ticket and issues a token.
  The hook returns TOML, like count and describe, so it
  can get richer later:

  ```toml
  ticket = "ticket-1"
  token = "token-1"
  ```

- Hook exit 0 means claimed. The CLI exits 0 and prints
  the hook output, the two TOML lines, and nothing else.
  The CLI prints the hook output verbatim, as the hook
  wrote it. A reversed order, or a TOML comment in the
  hook output, is printed as-is. Workpull does not
  re-render the ticket and token, because the token is
  opaque backend material and Workpull presents it
  unchanged.
- Hook exit non-zero means not claimed. The CLI preserves
  that exit code, and prints nothing.
- A missing hook means no claim. The CLI exits 2, and no
  claim is invented.
- Hook exit 0 with output that is not valid TOML means
  not claimed. The CLI exits 2, and prints nothing.
- Hook exit 0 with output that is not exactly a ticket
  and a token, each a non-empty string, means not
  claimed. The CLI exits 2, and prints nothing.
- The CLI does not validate a state. The backend
  validates it.

## Release

- `release <ticket> <token>`
- The token is a CLI argument. The CLI passes it to the
  release hook only through environment variables, never
  by interpolating it into the command string:
  `WORKPULL_TICKET` and `WORKPULL_TOKEN`.
- The backend validates the token against the claim on
  the ticket, and releases only if it matches. Workpull
  does not check the token itself.
- Hook exit 0 means released. The CLI exits 0 and prints
  the ticket id, and nothing else.
- Hook exit non-zero means not released. The CLI preserves
  that exit code, and prints no ticket id. That covers a
  wrong token, a ticket with no claim, and a race, as a
  hook failure.
- Hook exit 0 with empty stdout means not released. The
  CLI exits 2, and prints no ticket id.
- A missing hook means no release. The CLI exits 2, and
  no release is invented.

## Transition

- `transition <ticket> <to-state> <token>`
- The token is a CLI argument. Transition first checks,
  Workpull side, using the can-transition decision:
  get-state, describe, and count. Only if the check is
  true does transition call the transition hook.
- The CLI passes the token to the transition hook only
  through environment variables, never by interpolating
  it into the command string: `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`, and `WORKPULL_TOKEN`.
- The backend validates the token against the claim on
  the ticket, and moves only if it matches. Workpull
  does not check the token itself. Claim ends on the
  move.
- If the check is false, no move happens, the transition
  hook is not called, the CLI exits 2, and prints no
  ticket id.
- Hook exit 0 means transitioned. The CLI exits 0 and
  prints the ticket id, and nothing else.
- Hook exit non-zero means not transitioned. The CLI
  preserves that exit code, and prints no ticket id.
  That covers a wrong token and a race, as a hook
  failure.
- Hook exit 0 with empty stdout means not transitioned.
  The CLI exits 2, and prints no ticket id.
- A missing transition hook means no transition. The
  CLI exits 2, and no transition is invented.

## What it does not do

- Workpull does not store claims, does not issue tokens,
  and does not validate tokens.
- No state change in claim ticket or release. Claim
  ticket only acquires the lock; release only ends it.
