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
  `claim-ticket`, `transition`, `system-move`. Each
  hook command is the script plus its name, in
  canonical POSIX form.
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
  where the ticket is now.
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
  state file: work is tickets in that state with no
  waiting-for, wait is tickets waiting for it.
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
- `RELEASE_HOOK` and `LIST_WAITING_HOOK` are not in
  this step. Their contracts are written in designs
  010 and 016, and the mock grows them when a
  scenario needs them.

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
  ticket-1 in Backlog waiting for In Progress.
- Probe, one per hook, parametrized over the six
  hook names: run `mock_backend.py <hook>` directly,
  with the hook's correct env plus
  `WORKPULL_EXTRA=1`.
- Final state: the probe exits 1 with empty stdout,
  for every hook.

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
- No Event 10 backwards pull, and no `pull` command.
- No release or list-waiting in the mock yet.
- No real backend. The mock is test support only.
