# Design 019 — Pull command

## Command

- `pull`
- No arguments. The command sweeps the whole board:
  every state the backend's describe lists, in one
  run. There is no state argument, and no ticket
  argument: pull is by the state, not by a worker
  and not by a ticket. See requirement 004.

## Why a separate command

- Design 016 piggybacks the system move on
  transition, because every state change inside
  Workpull goes through transition. But a slot can
  open outside a transition: another actor's
  backend change, or a Workpull command that opens
  WIP and does not pull, like discard. The cascade
  never sees those slots.
- `pull` is the sweep design 016 deferred: it goes
  through all states and pulls, so slots opened
  elsewhere are filled on demand, in the run the
  operator asks for. There is still no daemon.

## The sweep

- The command fetches describe once, then visits
  the states in reverse describe order: the last
  state first, the first state last. Downstream
  states are served before their predecessors.
- In each state, the sweep loops:
  - Fetch a fresh count for the state. If its work
    count is at its work WIP limit, the state is
    done; move on to the next state.
  - List the tickets waiting for the state. If the
    list is empty, the state is done; move on.
  - Move the first ticket in the list, the highest
    priority waiting ticket, into the state, and
    print its ticket id.
  - Loop back to the fresh count.
- The fresh count is the only gate before each
  move, exactly as in the cascade. A slot filled
  by another actor between moves closes the gate
  at the next count, and the state is done.
- A state with an `inf` work limit always has
  capacity, so its loop ends only when its wait
  empties.
- One pass is enough. A ticket waiting for a state
  left an earlier state, because describe only
  allows a transition to a later state, and a
  waiting ticket counts as work in the state it
  left. Moving it out of wait opens a work slot
  there, and reverse order visits that earlier
  state later in the same run, where the fresh
  count sees the opened slot. This is a choice
  between readings of 004 and 016, made for this
  reason: the chain effect design 016 gets by
  walking predecessors one step at a time, the
  sweep gets by visiting every state downstream
  first. No repeated passes are needed.
- The sweep does not derive predecessors, the way
  the cascade does. The cascade starts from one
  opened slot and must find the state before it;
  the sweep visits every state anyway, so each
  state's own fresh count is all it needs. This
  is a deliberate simplification, chosen here:
  predecessor derivation, and its first-of-several
  ambiguity in design 016, belong to the cascade,
  not to the sweep.
- The sweep terminates. Each move takes one
  ticket out of one state's wait, waits are
  finite, and a moved ticket never re-enters a
  wait in the same run, because only transition
  puts a ticket into a wait and pull runs no
  transition. Each state is visited once.

## Hooks

- No new hooks. The sweep composes the hooks the
  cascade already uses, with the same contexts,
  the same output contracts, and the same failure
  shapes as design 016:
  - `DESCRIBE_HOOK`, fetched once, for the states,
    the order, and the WIP limits.
  - `COUNT_HOOK`, fresh before each move, for the
    capacity gate.
  - `LIST_WAITING_HOOK`, for the waiting tickets
    of one state, in priority order.
  - `SYSTEM_MOVE_HOOK`, for each move. The system
    is the mover: no claim, and no token.
- `LIST_WAITING_HOOK` unset means pulls are not
  configured. The sweep moves nothing and exits 0,
  silently, the same reading design 016 gives the
  cascade: a missing list hook is not an error.
  This is a choice, made for consistency with the
  cascade over erroring: the pull machinery is the
  same machinery in both commands, so its
  not-configured state means the same thing. In
  that configuration the count step is never
  reached, so a missing `COUNT_HOOK` is not an
  error there either.
- A missing hook a step needs is an error, as in
  the cascade: no `DESCRIBE_HOOK` or no
  `COUNT_HOOK` exits 2, and a `SYSTEM_MOVE_HOOK`
  unset when a move is attempted exits 2. No move
  is invented.

## Output

- Every moved ticket is printed, one per line, in
  the order moved, and nothing else on success.
  This is Satish's decision: the sweep's output is
  the record of the moves it made.
- A ticket is printed as its move completes, not
  collected and printed at the end. On a
  mid-sweep failure the tickets already printed
  name moves that stand, so the output stays a
  true record even on failure. This timing is a
  choice, made for that reason.

## Failure and exit codes

- If any hook fails mid-sweep — exits non-zero,
  returns invalid TOML, or returns no ticket id —
  the command stops at that step. Earlier pulls
  stand; nothing is rolled back. The CLI exits
  with the failing hook's code, or 2 for invalid
  hook output, exactly as a failed pull inside
  transition surfaces.
- A sweep that simply runs out of movable tickets
  exits 0: every state either reached its work
  limit or emptied its wait.

## What it does not do

- No claiming. A pulled ticket arrives in its new
  state unclaimed; `claim-ticket` still does the
  claiming.
- No forward push. The sweep never moves a ticket
  that is not waiting, and never starts new work:
  a slot with no ticket waiting for it stays open.
- No per-state or per-ticket pull. The command is
  the whole board or nothing.
- No daemon, no watch, no repeat. One run is one
  sweep.
