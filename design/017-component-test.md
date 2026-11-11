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
  `list-waiting`. Each hook command is the script
  plus its name, in canonical POSIX form.
- State is JSON, one file, read and written on every
  invocation, so state survives across hook calls:

  ```json
  {"tickets": [
    {"ticket": "ticket-1", "state": "Backlog",
     "priority": "a0", "token": null, "waiting_for": null}
  ]}
  ```

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
  order, first is highest. The mock issues a
  deterministic token per claim, `token-<ticket id>`
  for the ticket claimed, so the test can assert it
  and a token binds one claim to one ticket. A real
  backend decides its own token guarantees; the
  mock's token shape is a test simplification, stated
  here.
- The mock's describe is the same view as the
  transition unit tests: Backlog, In Progress, In
  Work, Done, with Backlog to In Progress, In
  Progress to Done, and the same WIP limits.

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
- `RELEASE_HOOK` is not in this step. Its contract
  is written in design 010, and the mock grows it
  when a scenario needs it.

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
  In Progress.
- Probe, one per hook, parametrized over the seven
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
  waiting ticket only, and stops there: one step,
  no cascade.
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
- Event 10 single step is in the mock: one waiting
  ticket pulled into the opened slot, no cascade.
  The two-step cascade is a later step, not this
  one, and there is no `pull` command yet.
- No release in the mock yet.
- No real backend. The mock is test support only.
