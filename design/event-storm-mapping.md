# Event storm mapping — what is covered, what is a gap

Each event storm item, mapped to requirements, design,
and implementation as they stand on branch 0.1, commit
5da818e. A gap is proved only where no mapping exists at
that level. Requirement covered does not mean designed,
and designed does not mean implemented.

## Events 1 to 12

### Event 1: Ticket Originated in Backlog

- Maps to: requirement 001, backend defines states,
  trivial system Backlog -> Done. Requirement 001,
  "Backlog is where prioritization happens."
- Gap, requirement: no. Gap, design / implementation:
  yes. There is no create / originate command, hook, or
  test. Ticket origination is a backend action, not a
  Workpull command, and that is not written down anywhere.

### Event 2: Backlog Prioritized

- Maps to: requirement 008, priority is a fractional
  order key, carried with the ticket, midpoint rule,
  never floats, rebalance when keys get too long.
  Refinement is per ticket, prioritization is a column
  activity, in design/ticket-lifetime.md Event 2.
- Gap, requirement: no. Gap, design / implementation:
  yes. There is no prioritization command, no
  claim-column command to lock the column for
  prioritization, and no hook contract for setting a
  fractional key. Claim-column is future only, in
  design 005.

### Event 3: Ticket Claimed

- Maps to: requirement 005, claim is a mutex,
  `claim-ticket <state>`, system picks top unclaimed ticket.
  Design 005, implementation 005, tests in
  tests/test_claim_ticket.py.
- Gap: no. Covered at all three levels, 37 tests pass.

### Event 4: Ticket Claimed to Refine It

- Maps to: Event 3. From the Workpull design standpoint,
  the actual activity does not matter. Refinement is the
  example activity. The step is claim.
- Gap: no. No separate refine command is needed, and none
  is claimed to be missing.

### Event 5: Signal Changed to Yellow

- Maps to: nothing. Rejected. Requirement 006, colors,
  archived as rejected in
  requirements/archive/006-ready-colors-rejected.md.
  Yellow / in work is now: claim held. No signal change
  command exists, and none is needed.
- Gap: no. This is a rejected concept, not a missing piece.

### Event 6: Signal Changed to Green

- Maps to: nothing, as a signal. Rejected, same archive.
  Replaced by requirement 006, Wait states: when work in
  a state is finished, the ticket moves into the wait
  state for the next state.
- Gap, requirement: no, wait states cover readiness.
  Gap, design / implementation: yes. There is no command
  or hook for the claimant to move a ticket into a wait
  state. No design, no implementation, no tests.

### Event 7: Claim Released

- Maps to: requirement 005, a claim ends when the ticket
  moves, when the actor releases it, or when the actor
  is gone. Design 005, release is a separate operation.
- Gap, requirement: no. Gap, design / implementation:
  yes. Release is a separate operation, and it has no
  design, no hook, no command, no tests.

### Event 8: Green Ticket Published

- Maps to: nothing. No requirement, design, or
  implementation mentions publish, broadcast, or
  subscribe. Requirement 004 says a slot-open system
  looks for tickets in the wait state, it does not say
  a wait-state ticket publishes its state and id, or
  that pullers subscribe to it.
- Gap: yes, at all three levels. Pub/sub is new, from
  event storming, not from requirements 001 to 008.

### Event 9: Ticket Claimed to Move It

- Maps to: requirement 005, claim ends on move, and
  requirement 007, transition moves a ticket.
  Design 005, `claim-ticket <state>`, system picks ticket.
- Gap, requirement: partial. Requirement 005 does not
  say who claims to move it, or that the downstream
  state / system is the claimant. That claimant is new,
  from event storming.
- Gap, design / implementation: yes. No puller claim,
  no move claim, no hook for it.

### Event 10: Ticket Moved to Next State

- Maps to: requirement 004, pull, and requirement 007,
  transition, only if the next state has capacity.
  Requirement 006, wait states, claim ends on move.
- Gap, requirement: no. Gap, design / implementation:
  yes. There is no pull command, no transition command,
  no hook, no tests. Pull and transition are
  requirements only.

### Event 11: Ticket Waits, No Capacity

- Maps to: requirement 004, if there is no ticket in
  the wait state, the slot stays open, and requirement
  007, if the next state is at its limit, the ticket
  stays in the wait state.
- Gap, requirement: no. Gap, design / implementation:
  yes, same as Event 10, no pull / transition
  implementation to enforce it.

### Event 12: Slot Opened in Next State

- Maps to: requirement 004, a slot comes open when its
  count drops below its WIP limit.
- Gap, requirement: no. Gap, design / implementation:
  yes. There is no slot-open event, listener, or command
  to look for wait-state tickets on a slot opening.
  That event is new, from event storming.

## Blocked

- Maps to: requirement 006, Blocked. A blocked ticket
  occupies WIP and keeps its priority. External blocker
  is a product manager conversation, keep priority with
  active work to unblock, reduce priority, or discard
  to open WIP and bring work back into the backlog.
- Gap, requirement: no. Gap, design / implementation:
  yes. There is no command, hook, or event for
  blocking, unblocking, or recording a blocker. Blocked
  is a rule, not a command.

## Claim-column

- Dropped 2026-11-08, by Satish. Column claim has no
  value. What is needed is a prioritization step that
  assigns priority values to tickets such that the values
  stay unique. That is all.
- Gap: no. This is a dropped concept, not a missing piece.

## Summary of proved gaps

- Design / implementation gaps, requirements covered:
  Event 1 origination, Event 2 prioritization /
  claim-column, Event 6 move to wait state, Event 7
  release, Event 10 pull / transition, Event 11 wait
  on no capacity, Event 12 slot-open lookup, Blocked
  as a command.
- Gaps at all levels, no requirement mapping:
  Event 8 publish / subscribe, and Event 9, who claims
  to move it, the downstream state / system as claimant.
- Not gaps: Event 3 claim-ticket, Event 4 refine as
  claim, Event 5 yellow as a signal, which is rejected,
  not missing.
