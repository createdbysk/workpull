# Design 017 — Component test with a mock backend

## Why

- The fake-hook tests prove each command in isolation.
  They do not prove the state after a run. A fake returns
  the count the test hands it, so a transition test can
  pass even if the ticket never moves.
- A component test sets up an initial state in a mock
  backend, runs Workpull commands against it through
  the CLI runner, and asserts the final state. The
  backend holds the state, not the test.
- The scenarios guard API-level invariants: command
  outcomes, claim order, and state as the commands
  present it, on boards that represent real runs.
  The mock's internal encodings are not guarded:
  they are the equipment's own bookkeeping, not
  the contract the commands answer to.

## Mock backend

- The mock backend lives in `tests/test_component.py`,
  next to the test that uses it, like the mock hook
  writers in the other test files. It is test support,
  not a backend, so it is not in `plugins/` or
  `adapters/`.
- It is one script, `mock_backend.py`, written into
  the isolated filesystem by `write_mock_backend`, with
  its state in `mock_backend_state.json` beside it.
  Every hook invocation is a subprocess, through the
  real `run_hook`, so the test proves the real hook
  path, not a fake.
- The script dispatches on its first argument, one
  name per hook: `describe`, `count`, `get-state`,
  `claim-ticket`, `transition`, `system-move`,
  `list-waiting`, `release`, `discard`, `adopt`,
  `prioritize`. Each hook command is the script
  plus its name, in canonical POSIX form.
- State is JSON, one file, read and written on every
  invocation, so state survives across hook calls:

  ```json
  {"tickets": [
    {"ticket": "ticket-1", "state": "Backlog",
     "priority": "a0", "token": null, "waiting_for": null}
  ],
   "unadopted": ["ticket-9"]}
  ```

- The state also lists backend tickets not yet
  adopted into Workpull, and counts the adopt keys
  it has issued, so an adopted ticket's key comes
  after every key ever issued, even a key whose
  ticket was later discarded. The count is backend
  bookkeeping, not part of the asserted state.

- A ticket has a work state, a priority key, a claim
  token or null, and a waiting-for state or null. A
  ticket in wait has `waiting_for` set to the state
  it waits for, and keeps its work state as the state
  it left. Its current state is the state it waits
  for, not the work state it left, because that is
  where the ticket is now. A ticket in wait occupies
  a work slot in the state it left, so pulling it out
  of wait opens a work slot there.
- Priority keys are strings, never floats, in priority
  order, first is highest. A key is a letter followed
  by digits, and the letter counts the digits: a0 to
  a9, then b10 to b99, then c100, so plain string
  order is priority order at any count. The mock issues a
  deterministic token per claim, `token-<ticket id>`
  for the ticket claimed, so the test can assert it
  and a token binds one claim to one ticket. A real
  backend decides its own token guarantees; the
  mock's token shape is a test simplification, stated
  here.
- The mock's describe is the same view as the
  transition unit tests: Backlog, In Progress, In
  Work, Done, with Backlog to In Progress, In
  Progress to Done, and the same WIP limits. The
  cascade tests use their own chained view
  instead: Backlog to In Progress, In Progress to
  In Work, In Work to Done, with the same WIP
  limits. `write_mock_backend_with_describe` takes
  the view explicitly; `write_mock_backend` is the
  same helper with the default view.

## Hooks

- `DESCRIBE_HOOK`, no env, prints the describe view.
- `COUNT_HOOK`, `WORKPULL_STATE` only, prints
  `wait` and `work` for that state, counted from the
  state file: work is tickets whose work state is
  that state, regardless of waiting-for, so a waiting
  ticket counts as work in the state it left; wait is
  tickets waiting for it. A waiting ticket counts in
  both, work in the state it left and wait in the
  state it waits for.
- `GET_STATE_HOOK`, `WORKPULL_TICKET` only, prints
  the ticket's current state: the state it waits for
  when it is in wait, otherwise its work state.
- `CLAIM_TICKET_HOOK`, `WORKPULL_STATE` only, picks
  the top unclaimed ticket in that state by priority,
  issues a token, stores it, prints TOML `ticket`
  and `token`. No unclaimed ticket in the state
  means exit 1, and no claim.
- `TRANSITION_HOOK`, `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`, `WORKPULL_TOKEN`, validates
  the token against the claim, moves the ticket to
  wait for the to-state, and ends the claim. A token
  that does not match means exit 1, and no move.
- `SYSTEM_MOVE_HOOK`, `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`, no token, moves the ticket
  from wait into the to-state. The system is the
  mover. A ticket not waiting for that state means
  exit 1, and no move.
- `LIST_WAITING_HOOK`, `WORKPULL_STATE` only, prints
  TOML `tickets = [...]`, the tickets waiting for
  that state in priority order, first is highest.
  An empty list means no ticket is waiting for it.
- `RELEASE_HOOK`, `WORKPULL_TICKET`,
  `WORKPULL_TOKEN`, validates the token against the
  claim, ends the claim, and prints the ticket id.
  The ticket keeps its state and its priority. A
  token that does not match means exit 1, and the
  claim stands.
- `DISCARD_HOOK`, `WORKPULL_TICKET`,
  `WORKPULL_TOKEN`, validates the token against the
  claim, removes the ticket from the backend
  entirely — no state, no priority, no claim — and
  prints the ticket id. The token is invalid
  afterwards. A token that does not match means
  exit 1, and no discard.
- `ADOPT_HOOK`, `WORKPULL_TICKET` only, adopts a
  backend ticket that is not in Workpull yet:
  assigns the first state in the describe view and
  the next priority key after every key ever
  issued, and prints the ticket id. A ticket
  already in the system means exit 1, and no
  adoption.
- `PRIORITIZE_HOOK`, `WORKPULL_TICKET`,
  `WORKPULL_AFTER`, moves the ticket to just after
  the after ticket, or to the top for
  `WORKPULL_TOP`, and prints the ticket id. The
  mock rebalances the keys in the new order,
  starting from a0: keys are backend-owned, so the
  order is the contract, not the key values. An
  unknown ticket or after ticket means exit 1, and
  no move.

## Scenario 1: transition with capacity, Event 8

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 and ticket-3 in In Progress,
  priorities a0 and a1, unclaimed. In Progress work
  is 2 of 3.
- Commands, through the CLI runner: claim-ticket
  Backlog, then transition ticket-1 to In Progress
  with the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-1 is In Progress; count In Progress is
  wait 0, work 3; the state file has ticket-1 in
  In Progress, waiting for nothing, with no token.
- The get-state and count assertions prove the final
  state through the CLI. The state file assertion
  proves it directly, including that the claim ended
  and the ticket is not in wait.

## Scenario 2: transition with no capacity, Event 9

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2, ticket-3, and ticket-4 in
  In Progress, priorities a0, a1, and a2, unclaimed.
  In Progress work is 3 of 3.
- Commands, through the CLI runner: claim-ticket
  Backlog, then transition ticket-1 to In Progress
  with the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-1 is In Progress, the state it waits for;
  count In Progress is wait 1, work 3; the state
  file has ticket-1 in Backlog, waiting for
  In Progress, with no token.
- Scenario 1 and Scenario 2 are one parametrized
  test, capacity_available and no_capacity_at_limit,
  sharing WHEN and THEN and differing only in GIVEN.

## Scenario 3: transition with another ticket's token

- Initial state: ticket-1 and ticket-2 in Backlog,
  priorities a0 and a1, unclaimed; ticket-3 in
  In Progress, priority a0, unclaimed.
- Commands, through the CLI runner: claim-ticket
  Backlog twice, then transition ticket-2 to
  In Progress with ticket-1's token.
- Final state: the transition exits 1 with empty
  output, and the state file is unchanged, both
  tickets still in Backlog holding their own tokens.

## Scenario 4: get-state of a waiting ticket

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed, waiting for In Progress.
- Command, through the CLI runner: get-state ticket-1.
- Final state: get-state returns In Progress, the
  state the ticket waits for, not the work state it
  left. A ticket's current state is where it is now.

## Scenario 5: mock backend rejects extra WORKPULL_ env

- Initial state, per hook: a state where the hook
  would succeed if the env were accepted, so only
  the env check can make it fail. Describe and count
  use an empty state; get-state and claim-ticket use
  ticket-1 in Backlog; transition uses ticket-1 in
  Backlog holding token-ticket-1; system-move uses
  ticket-1 in Backlog waiting for In Progress;
  list-waiting uses ticket-1 in Backlog waiting for
  In Progress; release and discard use ticket-1 in
  Backlog holding token-ticket-1; adopt uses
  ticket-9 not yet adopted; prioritize uses
  ticket-1 and ticket-2 in Backlog.
- Probe, one per hook, parametrized over the eleven
  hook names: run `mock_backend.py <hook>` directly,
  with the hook's correct env plus
  `WORKPULL_EXTRA=1`.
- Final state: the probe exits 1 with empty stdout,
  for every hook.

## Scenario 6: transition opens a slot, pulls one waiting ticket, Event 10

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 in In Progress, priority a0,
  unclaimed; ticket-3 in Backlog, priority a0,
  waiting for In Progress; ticket-4 in Backlog,
  priority a1, waiting for In Progress.
- Commands, through the CLI runner: claim-ticket
  In Progress, then transition ticket-2 to Done
  with the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-3 is In Progress, and get-state ticket-2
  is Done; count In Progress is wait 1, work 1,
  and count Done is wait 0, work 1; the state file
  has ticket-3 in In Progress, waiting for nothing,
  with no token, and ticket-4 still in Backlog,
  waiting for In Progress, priority and token
  unchanged. The pull takes the highest-priority
  waiting ticket, and the cascade steps back to
  Backlog and stops there: no ticket waits for
  Backlog, so its waiting list is empty.
- A second case covers the same transition with
  `LIST_WAITING_HOOK` unset: it succeeds, and the
  waiting ticket stays waiting, because Event 10
  is not configured. The two cases are one
  parametrized test, sharing WHEN and THEN and
  differing only in GIVEN.

## Scenario 7: count of a waiting ticket

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed, waiting for In Progress; ticket-2 in
  In Progress, priority a0, unclaimed.
- Commands, through the CLI runner: count Backlog,
  then count In Progress.
- Final state: count Backlog is wait 0, work 1, and
  count In Progress is wait 1, work 1. A waiting
  ticket counts as work in the state it left and as
  wait in the state it waits for.

## Scenario 8: pull after Event 9

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2, ticket-3, and ticket-4 in
  In Progress, priorities a0, a1, and a2, unclaimed,
  so In Progress work is 3 of 3; ticket-5 in Backlog,
  priority a0, waiting for Backlog.
- Ticket-5 is set up directly in the mock state: a
  ticket waiting for Backlog cannot arise through
  transition, because no transition targets Backlog,
  so it is artificial here, to prove the pull runs
  after Event 9.
- Commands, through the CLI runner: claim-ticket
  Backlog, then transition ticket-1 to In Progress
  with the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-1 is In Progress, the state it waits for,
  and get-state ticket-5 is Backlog; count
  In Progress is wait 1, work 3, and count Backlog
  is wait 0, work 2; the state file has ticket-1 in
  Backlog, waiting for In Progress, with no token,
  and ticket-5 in Backlog, waiting for nothing, with
  no token. The pull runs even though Event 8 did
  not move the transitioning ticket.

## Scenario 9: a waiting ticket counts as work, so Event 8 does not move

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 and ticket-3 in In Progress,
  priorities a0 and a1, unclaimed; ticket-4 in
  In Progress, priority a2, unclaimed, waiting for
  Done. In Progress work is 3 of 3: ticket-2,
  ticket-3, and ticket-4, which counts as work in
  the state it left even though it waits for Done.
- Commands, through the CLI runner: claim-ticket
  Backlog, then transition ticket-1 to In Progress
  with the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-1 is In Progress, the state it waits for;
  count In Progress is wait 1, work 3; the state
  file has ticket-1 in Backlog, waiting for
  In Progress, with no token, and ticket-4 still in
  In Progress, waiting for Done. The waiting ticket
  is what fills the third work slot, so the Event 8
  decision changes: under the old count, work would
  be 2 of 3 and ticket-1 would move.
- This case is in the parametrized transition test,
  sharing WHEN and THEN with Scenarios 1 and 2 and
  differing only in GIVEN.

## Scenario 10: three-step cascade, Event 10

- Initial state, under the chained view: ticket-1
  in Backlog, priority a0, unclaimed; ticket-2 in
  In Work, priority a0, unclaimed; ticket-3 in
  In Progress, priority a0, unclaimed, waiting for
  In Work; ticket-4 in Backlog, priority a0,
  unclaimed, waiting for In Progress; ticket-5 in
  Backlog, priority a1, unclaimed, waiting for
  Backlog. Ticket-5 is artificial, as Scenario 8
  does: a ticket waiting for Backlog cannot arise
  through transition, because no transition targets
  Backlog, and it waits for the state it is already
  in. It is there so the test can tell a capped
  cascade from N steps: the third pull moves it,
  and a cascade capped at two steps leaves it
  waiting.
- Commands, through the CLI runner: claim-ticket
  In Work, then transition ticket-2 to Done with
  the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-3 is In Work, get-state ticket-4 is
  In Progress, and get-state ticket-2 is Done;
  count In Work is wait 0, work 1, count
  In Progress is wait 0, work 1, count Done is
  wait 0, work 1, and count Backlog is wait 0,
  work 2; the state file has ticket-3 in
  In Work, ticket-4 in In Progress, ticket-5 in
  Backlog, and ticket-2 in Done, each waiting for
  nothing, with no token.
  The first pull moves ticket-3 into In Work, and
  that move triggers the second pull, ticket-4 into
  In Progress, and that move triggers the third
  pull, ticket-5 into Backlog, one step backwards
  at a time toward Backlog. Backlog has no
  predecessor, so the cascade stops there.

## Scenario 11: cascade stops at the second pull's capacity gate, Event 10

- Initial state, under the chained view: ticket-1
  in Backlog, priority a0, unclaimed; ticket-2 in
  In Work, priority a0, unclaimed; ticket-3 in
  In Progress, priority a0, unclaimed, waiting for
  In Work; ticket-4 in Backlog, priority a0,
  unclaimed, waiting for In Progress; ticket-6,
  ticket-7, and ticket-8 in In Progress, priorities
  a0, a1, and a2, unclaimed, so In Progress work
  is 3 of 3.
- Commands, through the CLI runner: claim-ticket
  In Work, then transition ticket-2 to Done with
  the token the claim returned.
- Final state, asserted three ways: get-state
  ticket-3 is In Work, get-state ticket-4 is
  In Progress, and get-state ticket-2 is Done;
  count In Work is wait 0, work 1, count
  In Progress is wait 1, work 3, and count Done
  is wait 0, work 1; the state file has ticket-3
  in In Work, ticket-4 still in Backlog, waiting
  for In Progress, and ticket-2 in Done, each
  waiting for nothing except ticket-4, with no
  token. The transition and the first pull stand
  even though the second pull did not happen:
  a cascade failure, or a stop at the second
  pull's capacity gate, leaves earlier moves
  applied, nothing is rolled back.

## Scenario 12: discard removes a claimed ticket

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 and ticket-3 in In Progress,
  priorities a0 and a1, unclaimed.
- Commands, through the CLI runner: claim-ticket
  Backlog, then discard ticket-1 with the token the
  claim returned.
- Final state, asserted three ways: get-state
  ticket-1 exits 1, because the ticket is gone;
  count Backlog is wait 0, work 0, and count
  In Progress is wait 0, work 2; the state file
  holds only ticket-2 and ticket-3. The discarded
  ticket counts against no state's WIP.

## Scenario 13: token invalid after discard

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 in In Progress, priority a0,
  unclaimed.
- Commands, through the CLI runner: claim-ticket
  Backlog, discard ticket-1 with its token, then
  release, transition, and discard again, each
  presenting the same token.
- Final state: each of the three later commands
  exits 1 with empty output, and the state file
  holds only ticket-2. Discard ends the claim, and
  the token buys nothing afterwards.

## Scenario 14: discard with another ticket's token

- Initial state: ticket-1 and ticket-2 in Backlog,
  priorities a0 and a1, unclaimed; ticket-3 in
  In Progress, priority a0, unclaimed.
- Commands, through the CLI runner: claim-ticket
  Backlog twice, then discard ticket-1 with
  ticket-2's token.
- Final state: the discard exits 1 with empty
  output, and the state file is unchanged, both
  tickets still in Backlog holding their own
  tokens. This is Scenario 3's shape, for discard.

## Scenario 15: discard of a ticket with no claim

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed.
- Command, through the CLI runner: discard
  ticket-1 with token-ticket-1.
- Final state: the discard exits 1 with empty
  output, and the state file is unchanged. There
  is no claim to discard, so the token matches
  nothing. Only a ticket with a claim can be
  discarded.

## Scenario 16: release ends the claim, ticket claimed again

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed; ticket-2 in In Progress, priority a0,
  unclaimed.
- Commands, through the CLI runner: claim-ticket
  Backlog, release ticket-1 with the token the
  claim returned, transition ticket-1 to
  In Progress with the same token, claim-ticket
  Backlog again, then get-state ticket-1.
- Final state: the release exits 0 and prints
  ticket-1; the transition exits 1, because the
  claim is gone and its token buys nothing; the
  second claim returns ticket-1 with a token, and
  get-state returns Backlog; the state file has
  ticket-1 in Backlog, priority a0, holding the
  second claim's token, its state and priority
  untouched by the release. The mock issues
  `token-<ticket id>` per claim, so the second
  token is the same string; the scenario proves
  the fresh claim, not a new string.

## Scenario 17: release with another ticket's token

- Initial state and commands are Scenario 14's,
  with release in place of discard.
- Final state: the release exits 1 with empty
  output, and the state file is unchanged, both
  tickets still in Backlog holding their own
  tokens. A token releases only its own claim.

## Scenario 18: adopt assigns first state and lowest priority

- Initial state: ticket-1 and ticket-2 in Backlog,
  priorities a0 and a1, unclaimed; ticket-3 exists
  in the backend, not yet adopted.
- Commands, through the CLI runner: adopt
  ticket-3, then claim-ticket Backlog three times.
- Final state: adopt prints ticket-3; the claims
  return ticket-1, ticket-2, and ticket-3, in that
  order — adoption order is priority order, and
  the adopted ticket is last; the state file has
  ticket-3 in Backlog, priority a2, and no ticket
  left unadopted.

## Scenario 19: adopt rejects a ticket already in the system

- Two cases, one parametrized test: ticket-1
  already adopted, in Backlog; ticket-1 already in
  progress, in In Progress.
- Command, through the CLI runner: adopt ticket-1.
- Final state: the adopt exits 1 with empty
  output, and the state file is unchanged. Adopt
  only takes a ticket that is not in the system
  yet.

## Scenario 20: prioritize reorders tickets

- Two cases, one parametrized test, sharing WHEN
  and THEN and differing only in GIVEN: move
  ticket-1 to just after ticket-3, the last
  ticket; move ticket-3 to the top, with
  `WORKPULL_TOP`. Both start from ticket-1,
  ticket-2, and ticket-3 in Backlog, priorities
  a0, a1, and a2, unclaimed.
- Commands, through the CLI runner: prioritize,
  then claim-ticket Backlog.
- Final state: the claim returns the new top
  ticket — ticket-2 in the first case, ticket-3
  in the second — and the state file shows the
  new order in the priority keys, rebalanced to
  a0, a1, a2. Priority order is one order across
  states; the move carries no state change.

## Scenario 21: prioritize with an unknown after ticket

- Initial state: ticket-1 and ticket-2 in Backlog,
  priorities a0 and a1, unclaimed.
- Command, through the CLI runner: prioritize
  ticket-1 after ticket-9.
- Final state: the prioritize exits 1 with empty
  output, and the state file is unchanged. The
  backend validates the after ticket.

## Scenario 22: can-transition answers from backend facts

- Four cases, one parametrized test, sharing WHEN
  and THEN and differing only in GIVEN: a move
  reachable with wait capacity answers true; a
  move the describe transitions do not allow
  answers false; an unknown to-state answers
  false; a to-state whose wait count is at its
  wait limit answers false.
- Command, through the CLI runner: can-transition.
- Final state: the printed word matches the case,
  the command exits 0, and the state file is
  unchanged. Can-transition has no hook of its
  own: it composes get-state, describe, and count,
  so the mock needs no new hook for it, and the
  scenario runs the command itself, not only the
  check inside transition.

## Scenario 23: describe prints the mock backend's view

- Initial state: no tickets.
- Command, through the CLI runner: describe.
- Final state: the CLI prints the mock's view,
  normalized: the four states, Backlog to
  In Progress and In Progress to Done, and the
  WIP limits. The describe hook otherwise runs
  inside transition and can-transition; this
  scenario runs the command itself.

## Scenario 24: release of a ticket with no claim

- Initial state: ticket-1 in Backlog, priority a0,
  unclaimed.
- Command, through the CLI runner: release
  ticket-1 with token-ticket-1.
- Final state: the release exits 1 with empty
  output, and the state file is unchanged. There
  is no claim to release, so the token matches
  nothing. This is Scenario 15's shape, for
  release.

## Scenario 25: adopt with many tickets, adopted ticket is last

- Initial state: ticket-1 to ticket-11 in Backlog,
  priorities a0 to a9 and b10, unclaimed;
  ticket-12 exists in the backend, not yet
  adopted.
- Commands, through the CLI runner: adopt
  ticket-12, then claim-ticket Backlog twelve
  times.
- Final state: the claims return ticket-1 to
  ticket-12, in that order; the state file has
  ticket-12 in Backlog, priority b11, and no
  ticket left unadopted. The adopted ticket is
  claimed last, so the lowest-priority rule holds
  past the single-digit keys.

## Scenario 26: adopt two tickets, keys increase in adoption order

- Initial state: ticket-1 in Backlog, priority
  a0, unclaimed; ticket-2 and ticket-3 exist in
  the backend, not yet adopted.
- Commands, through the CLI runner: adopt
  ticket-2, adopt ticket-3, then claim-ticket
  Backlog three times.
- Final state: the claims return ticket-1,
  ticket-2, and ticket-3, in that order; the
  state file has ticket-2 at priority a1 and
  ticket-3 at priority a2, and no ticket left
  unadopted. The adopt counter moves on with each
  adoption, so each issued key is strictly after
  the one before it.

## Scenario 27: adopt after discarding the highest key

- Initial state: ticket-1 and ticket-2 in
  Backlog, priorities a0 and a1, unclaimed;
  ticket-3 exists in the backend, not yet
  adopted.
- Commands, through the CLI runner: claim-ticket
  Backlog twice, discard ticket-2 with its token,
  adopt ticket-3, then claim-ticket Backlog.
- Final state: the claim returns ticket-3; the
  state file has ticket-1 in Backlog, priority
  a0, holding its claim token, ticket-3 in
  Backlog, priority a2, holding the last claim's
  token, and no ticket left unadopted. The issued
  key comes after a1, the highest key ever
  issued, even though its ticket was discarded:
  the counter counts keys issued, not keys in
  use.

## Visual board

- A read-only board over the mock backend state file
  would help this test: one page, states as columns,
  tickets in work and wait, WIP counts, claims, and
  priority order, before and after the run. No
  editing, no auth, no backend of its own.
- It is not built in this step. The component test
  comes first, and the board follows only if reading
  the state file proves hard to see.

## What it does not do

- No new production code, and no new command.
- Event 10 N-step cascade is in the mock: the
  chain pulls backwards while each pull moves a
  ticket, and there is no `pull` command yet.
- No command is left without a scenario: the
  earlier scenarios run count, get-state,
  claim-ticket, transition, system-move, and
  list-waiting; Scenarios 12 to 23 add release,
  discard, adopt, prioritize, can-transition, and
  describe. Scenario 24 adds the release failure
  with no claim. Scenarios 25 to 27 cover
  adoption on fuller boards: the adopted ticket
  is claimed last, claim order follows adoption
  order across two adoptions, and an adoption
  after a discard still lands last.
- No real backend. The mock is test support only.
