# Ticket lifetime — event storming

DDD event storming, one event at a time. Domain events are
in the past tense, in the ubiquitous language of
requirements 004 to 008: state, signal, claim, pull, WIP
limit. A signal is not a state. Claim is a mutex, not a
move. Signals are white unclaimed, green ready, yellow in
work, red blocked.

## Event 1: Ticket Originated in Backlog

Backlog is an example state, not a required state. Some
systems have no backlog. The first state is whatever the
backend defines in describe.

- State: Backlog, example
- Signal: White, unclaimed
- Claim: None, no actor holds it
- WIP: In this example, Backlog is unbounded, WIP limit
  inf, so entry never waits for a slot

A ticket originates in Backlog, in this example. There is
no earlier event.

## Event 2: Backlog Prioritized

Gap found by event storming: a ticket cannot be claimed
from Backlog until Backlog has been prioritized.

Refinement and prioritization are different steps.
Refinement is per ticket. Prioritization is a column
activity, ordering the tickets in a column.

Prioritization is one reason to claim a column, not the
only reason. A column claim is a mutex on the whole
column. No other reason is in mind, and none is invented
here.

- State: Backlog, example, unchanged
- Signal: White, unchanged
- Claim: None, no actor holds it
- Priority: Set by prioritization, a column activity,
  top to bottom, as a fractional order key carried with
  the ticket. A ticket inserted between two tickets
  takes the midpoint key between theirs. A ticket
  inserted after the last ticket takes a key after the
  last key. Order keys are stored as strings or
  arbitrary-precision decimals, never as floats. When
  keys get too long, the column is rebalanced once, back
  to short keys. The ticket carries that key until Done,
  unless a business priority change reprioritizes it
  mid-flight, giving it a new order key.

## Event 3: Ticket Claimed

- State: Backlog, example, unchanged
- Signal: White, unchanged, claim does not change the
  signal
- Claim: Held, by the actor who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, and returned it to that actor.
- WIP: Still counts against Backlog

## Event 4: Ticket Claimed to Refine It

From the Workpull design standpoint, the actual activity
does not matter. Refinement is the example activity here.
The step is claim, then the claimant changes the signal
to yellow.

- State: Backlog, example, unchanged. Backlog is inf
  WIP in this example.
- Signal: White, unchanged, claim does not change the
  signal
- Claim: Held, by the product manager who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, in priority order, and returned it
  to that actor.
- WIP: Still counts against Backlog

## Event 5: Signal Changed to Yellow

- State: Backlog, example, unchanged
- Signal: Yellow, in work, changed by the claiming
  actor after the claim
- Claim: Held, unchanged
- WIP: Still counts against Backlog

## Event 6: Signal Changed to Green

The product manager refines the ticket. When refinement
is complete, they mark the ticket green. The actual
activity does not matter for Workpull design; refinement
is the example activity here.

- State: Backlog, example, unchanged
- Signal: Green, ready to move, changed by the claiming
  actor when the work in this state is finished
- Claim: Held, unchanged. Marking green does not end the
  claim. The claim ends on move, release, or the actor
  going away.
- WIP: Still counts against Backlog

## Event 7: Claim Released

The product manager releases the claim.

- State: Backlog, example, unchanged
- Signal: Green, ready to move, unchanged. Releasing the
  claim does not change the signal.
- Claim: Released, no actor holds it. The ticket is now
  unclaimed and green.
- WIP: Still counts against Backlog

## Event 8: Green Ticket Published

When a ticket goes green, the system publishes its state
and id.

- State: Backlog, example, unchanged
- Signal: Green, ready to move, unchanged
- Claim: None, unchanged
- Publication: State and id published. Work pullers
  subscribe to this signal, per state. The puller for
  the next state is subscribed to green events from its
  predecessor states.
- WIP: Still counts against Backlog

## Event 9: Ticket Claimed to Move It

The puller for the next state claims the ticket to move
it, to prevent races. The claimant is the downstream
state, the system doing the pull, not a human worker.

- State: Backlog, example, unchanged
- Signal: Green, unchanged, claim does not change the
  signal
- Claim: Held, by the puller for the next state
- WIP: Still counts against Backlog

## Event 10: Ticket Moved to Next State

The puller for the next state pulls the ticket, if its
state has capacity, below its WIP limit. The green
broadcast is only for a move into a capacity-available
slot.

## Event 11: Ticket Waits, No Capacity

If the next state has no capacity, the ticket just waits.

- State: Backlog, example, unchanged
- Signal: Green, ready to move, unchanged
- Claim: None, unchanged. No claim to move is made.
- WIP: Still counts against Backlog

## Event 12: Slot Opened in Next State

When the next state has capacity, that is an event to
look for green tickets to move.

- State: Next state, example, unchanged, now below its
  WIP limit
- Signal: No change to this ticket yet
- Claim: None, unchanged
- Action: The puller for the next state looks for green
  tickets in its predecessor states, highest priority
  first, and pulls one per open slot, as in Event 9 and
  Event 10.

- State: Next state, example, changed from Backlog
- Signal: White, reset on move, unclaimed, no work
  started in the new state yet
- Claim: Ended on the move, no actor holds it
- Priority: Carried with the ticket, as a fractional
  order key. The ticket takes its priority position in
  the new state by that key, not by arrival order.
- WIP: Now counts against the next state, no longer
  against Backlog
