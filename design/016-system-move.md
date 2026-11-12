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
  in the upstream state, which pulls from its wait
  once more. Two steps only, in this step; see
  "Event 10: Two-step cascade".
- The chain runs backwards, one state at a time,
  and stops at Backlog, the first state. It never
  runs forward, from a state into its next state
  and onward to Done.

## Event 10: Slot Opened in Next State, single step (previous step)

- The ticket moving out of its old state opens a
  slot there. Workpull checks the old state's wait
  queue, and pulls the highest priority waiting
  ticket into it, one per open slot.
- Single step was the previous step: the pull moved
  exactly one waiting ticket into the opened slot,
  and stopped there. No recursion, no loop over
  upstream states, no second pull in the same
  command. The two-step cascade, in the next
  section, builds on this single step and is the
  current behaviour.
- That pull is a second system move, in the same
  transition command, after Event 8. It uses
  `LIST_WAITING_HOOK` to find the waiting ticket
  and `SYSTEM_MOVE_HOOK` to move it, with no
  token, the system is the mover.
- `LIST_WAITING_HOOK` unset means Event 10 is not
  configured. Transition proceeds without a pull,
  silently, with its old behaviour. A missing
  list hook is not an error, and `_fetch_waiting_tickets`
  is only called when the hook is set, so it has no
  missing-hook branch.
- The pull runs even when Event 8 did not move the
  transitioning ticket, Event 9. The slot in the
  old state still opened, so the waiting ticket
  there is still pulled.
- The pull re-fetches the old state's count at pull
  time, it does not reuse the count from the
  can-transition check. A slot filled by another
  actor between the transition and the pull can
  leave the old state at its work limit, so the
  pull checks capacity again and skips the list
  when there is none.

## Event 10: Two-step cascade

- The cascade is triggered by the move itself,
  not by a re-fetched count. When a pull moves a
  ticket out of its wait into a state, that move
  triggers the next pull, from the wait of the
  state the pulled ticket left, one step backwards
  toward Backlog. The fresh count at pull time is
  only the gate, not the trigger.
- "The state the pulled ticket left" is derived
  from describe transitions, not from any hook:
  the state whose transition target is the pulled
  ticket's new state, the state before it. No hook
  returns that value, so Workpull derives it from
  describe.
- That derivation assumes one predecessor per
  target. Two states can transition to the same
  target, which makes the predecessor ambiguous,
  and in that case Workpull pulls from the first
  predecessor in the states list. That choice is
  documented here, not hidden in the code.
- A waiting ticket occupies a work slot in the state
  it left, so pulling it out of wait opens a work
  slot there. Count's work is tickets whose work
  state is that state, regardless of waiting-for,
  and wait is tickets waiting for that state. A
  waiting ticket counts as work in the state it
  left and as wait in the state it waits for.
- Each cascade step pulls exactly one ticket, the
  highest priority waiting ticket for the state it
  pulls into, one per open slot. A move opens
  exactly one slot, so a step pulls one ticket.
- Each cascade step is gated by a capacity
  re-check in the state it pulls into, a fresh count
  at pull time. The move just opened one slot there,
  so the gate normally passes, but a slot filled by
  another actor between the move and the pull can
  close it, so the gate stays.
- A cascade failure leaves earlier moves applied. If
  the second pull fails — a hook exits non-zero,
  returns invalid TOML, or returns no ticket id —
  or stops at its capacity gate, the transition
  and the first pull stand; nothing is rolled back.
  The CLI exits with the failing hook's code on a
  failure, and 0 when the second pull stops at the
  gate, and prints no ticket id on a failure.
- Two steps only, in this step: the first pull into
  the opened slot, and the second pull into the
  state the first pulled ticket left. No third pull,
  no generalization to N steps yet.
- The two-step cascade test uses a chained
  four-state describe view, Backlog -> In Progress
  -> In Work -> Done, not an artificial mock state.
  The current describe view is not chained, In
  Progress goes straight to Done and In Work is
  isolated, so the two-step test needs its own view.

## Who moves

- The system moves the tickets, in both cases. Not
  a worker, and not a claim. There is no claim to
  move a ticket, and no token to present for a system
  move. The system is the mover.
- Priority is carried, unchanged. WIP counts against
  the to-state after the move, no longer against the
  wait state.

## List waiting tickets, and move a ticket from wait into work

- Count gives numbers only, not ticket ids or
  priorities, so Workpull lists which waiting
  ticket to pull through `LIST_WAITING_HOOK`, and
  moves it through `SYSTEM_MOVE_HOOK`. Both hooks
  are implemented, not proposed.

### List waiting tickets

- Hook: `LIST_WAITING_HOOK`, an environment
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
- Hook exit 0 with output that is not valid TOML
  means not listed. The CLI exits 2, and no system
  move happens on that list.
- Hook exit 0 with output that is not exactly
  `tickets`, a list of non-empty strings, means not
  listed. The CLI exits 2, and no system move
  happens on that list.
- There is no non-dict check on the document:
  `tomllib.loads` always returns a dict, so no
  input can reach a non-dict document.
- A missing hook means Event 10 is not configured.
  Transition proceeds without a pull, silently.
  `_fetch_waiting_tickets` is only called when the
  hook is set.

### Move a ticket from wait into work

- Hook: `SYSTEM_MOVE_HOOK`, an environment
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
  fetch returns both fields, so the can-transition
  decision and the capacity check share one count of
  the to-state. Transition fetches describe once, and
  count once per state: the to-state in the check, and
  the old state in the pull.
- No forward cascade. The system never pushes a
  ticket onward, state to state, all the way to
  Done, in one command. The pull chain runs
  backwards, toward Backlog, and stops there.
- Event 10 two-step cascade is this step: two pulls,
  the first into the opened slot and the second into
  the state the first pulled ticket left, no third
  pull. Generalization to N steps is a later step,
  not this one.
