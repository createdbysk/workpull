# Design 016 — System move, piggybacked on transition

## Trigger

- Transition is the only reliable trigger for the system
  move, because every state change goes through
  transition. There is no daemon, and Workpull only
  runs when an actor runs it. The system comes into
  the picture only inside a Workpull command.
- The system move is piggybacked on transition, in
  the same transition command, after the transition
  hook has moved the ticket into the wait state for
  the to-state. It is not a separate command, and
  it is not a separate run.
- A separate `pull` command, that goes through all
  states and pulls, is a later step, not this one.
  Claim and count do not change states, so a sweep
  there would only catch slots opened elsewhere, by
  chance. Transition is the one clients can rely on,
  because it is the only command that explicitly
  causes the moves that change states.

## Event 8: Ticket Moved Immediately, Capacity Available

- After transition moves a ticket into the wait state
  for the to-state, Workpull checks the to-state for
  work capacity, using count and describe: the
  to-state's work count, against its work limit from
  describe. An `inf` work limit always has capacity.
- If there is capacity, the system moves the ticket
  straight from the wait state into the to-state, in
  the same transition command. The ticket takes its
  priority position in the new state by its key, not
  by arrival order.
- If there is no capacity, the ticket stays in the
  wait state. That is Event 9, and no system move
  happens for it in this command.
- Event 8 is one move, of this ticket, into this
  to-state. It is not the start of a forward cascade
  to Done. The system does not keep pushing this
  ticket onward into the next state after that.

## Pull is backwards, not a forward cascade

- The cascade is not all the way to Done. Pull is
  backwards, toward Backlog.
- When a slot opens in a downstream state, the system
  pulls from that state's wait, highest priority
  first, one per open slot. That move opens a slot
  in the upstream state, which pulls from its wait,
  and so on backwards toward Backlog.
- The chain runs backwards, one state at a time,
  and stops at Backlog, the first state. It never
  runs forward, from a state into its next state
  and onward to Done.

## Event 10: Slot Opened in Next State

- The ticket moving out of its old state opens a
  slot there. Workpull checks the old state's wait
  queue, and pulls the highest priority waiting
  ticket into it, one per open slot.
- That pull is the start of the backwards chain in
  the section above: the pulled ticket leaving its
  wait opens a slot upstream, which pulls from its
  wait, and so on backwards toward Backlog.
- This is a second system move, in the same
  transition command, after Event 8. Its test comes
  after the Event 8 happy path, one at a time.
  This step covers Event 8 only.

## Who moves

- The system moves the tickets, in both cases. Not
  a worker, and not a claim. There is no claim to
  move a ticket, and no token to present for a system
  move. The system is the mover.
- Priority is carried, unchanged. WIP counts against
  the to-state after the move, no longer against the
  wait state.

## Open gap: Workpull cannot list waiting tickets yet

- Count gives numbers only, not ticket ids or
  priorities, so Workpull cannot yet list which
  waiting ticket to pull, for Event 10, and cannot
  yet prove which ticket is waiting for a state.
- This gap is not invented past. Two backend hooks
  are needed, proposed here, not implemented yet:

### List waiting tickets

- Proposed hook: `LIST_WAITING_HOOK`, an environment
  variable, not a CLI parameter.
- Context only through environment variables, never
  by interpolating values into the command string:
  `WORKPULL_STATE` only.
- The hook returns TOML, like describe and count, so
  it can get richer later:

  ```toml
  tickets = ["ticket-2", "ticket-3"]
  ```

- The list is in priority order, first is highest
  priority. An empty list means no ticket is waiting
  for that state.
- Hook exit 0 means listed. The CLI exits 0 for the
  listing step, and uses the list to decide the pull.
- Hook exit non-zero means not listed. The CLI
  preserves that exit code, and no system move
  happens on that list.
- A missing hook means no list. The CLI exits 2, and
  no system move happens on that list.
- Hook exit 0 with output that is not valid TOML
  means not listed. The CLI exits 2, and no system
  move happens on that list.
- Hook exit 0 with output that is not exactly
  `tickets`, a list of non-empty strings, means not
  listed. The CLI exits 2, and no system move
  happens on that list.

### Move a ticket from wait into work

- Proposed hook: `SYSTEM_MOVE_HOOK`, an environment
  variable, not a CLI parameter.
- Context only through environment variables, never
  by interpolating values into the command string:
  `WORKPULL_TICKET` and `WORKPULL_TO_STATE`. No
  `WORKPULL_TOKEN`: the system is the mover, there
  is no claim to move it, and no token to present.
- Hook exit 0 means moved. The hook prints the
  ticket id, and nothing else, like transition.
- Hook exit non-zero means not moved. The CLI
  preserves that exit code, and prints no ticket id.
- Hook exit 0 with empty stdout means not moved.
  The CLI exits 2, and prints no ticket id.
- A missing hook means no move. The CLI exits 2, and
  no move is invented.

## TransitionCheck work_count

- When the to-state is not in describe, count is not
  fetched, so `TransitionCheck.work_count` has no count
  behind it. It is undefined when `allowed` is False,
  and transition must never read it there. The
  placeholder value does not matter.
- The count is not fetched first: the count hook is not
  called for a state that does not exist.

## What it does not do

- No new command in this step. No `pull` command yet.
- No claim, no token, and no actor choice in the
  system move. The actor who called transition does
  not choose which ticket the system moves.
- The work capacity check reuses count, which returns both
  `wait` and `work` in one TOML document. One shared
  fetch returns both fields, so transition fetches
  describe and count once, and shares the results
  between the can-transition decision and the capacity
  check.
- No forward cascade. The system never pushes a
  ticket onward, state to state, all the way to
  Done, in one command. The pull chain runs
  backwards, toward Backlog, and stops there.
- Event 10 is designed here, and its test and green
  come after the Event 8 happy path, one at a time.
