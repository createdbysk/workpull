# Ticket lifetime — event storming

DDD event storming, one event at a time. Domain events are
in the past tense, in the ubiquitous language of
requirements 004 to 008: state, claim, pull, WIP limit,
wait state, priority. A signal is not a state. There are
no colors and no signals on a ticket. A ticket has a
state, a claim, and a priority, and nothing else.
Claim is a mutex, not a move. Readiness to move is a
wait state, a separate state, not a color.

States named here, Backlog, and the next states in the
example, are examples, not required states. Some systems
have no backlog. The first state is whatever the backend
defines in describe.

## Event 1: Ticket Originated in Backlog

- State: Backlog, example
- Claim: None, no actor holds it
- Priority: Not yet set
- WIP: In this example, Backlog is unbounded, WIP limit
  inf, so entry never waits for a slot

A ticket originates in Backlog, in this example. There is
no earlier event.

Anyone can create a ticket, and it arrives into the first
state. Most systems have a triage step, where a claim is
to triage a ticket and decide whether it belongs in the
backlog. That is a system specific concept, and not a
concern of Workpull. Some entity creates the ticket and
it starts in the first state. The entity depends on the
system itself, and is not a concern of Workpull.
Workpull does not implement a create at all. Anyone
should be able to use the native backend system to
create the tickets. Workpull is extremely specific to
a particular use case, overlayed on that system.

## Event 2: Backlog Prioritized

A ticket cannot be claimed from Backlog until Backlog
has been prioritized.

Refinement and prioritization are different steps.
Refinement is per ticket. Prioritization is a column
activity, ordering the tickets in a column.

Column claim has no value, and is dropped. What is
needed is a prioritization step that assigns priority
values to tickets such that the values stay unique.
That is all.

There is no begin / end lock for prioritization.
Prioritize as a move between tickets. The system can
error if there is a conflict. It is a low occurrence
race.

- State: Backlog, example, unchanged
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
- Claim: Held, by the actor who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, and returned it to that actor.
- Priority: Carried, unchanged
- WIP: Still counts against Backlog

## Event 4: Ticket Claimed to Refine It

From the Workpull design standpoint, the actual activity
does not matter. Refinement is the example activity here.
The step is claim, then work.

- State: Backlog, example, unchanged. Backlog is inf
  WIP in this example.
- Claim: Held, by the product manager who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, in priority order, and returned it
  to that actor.
- Priority: Carried, unchanged
- WIP: Still counts against Backlog

## Event 5: Work Started

The claiming actor works on the ticket. Claim held is
in work. There is no signal change.

- State: Backlog, example, unchanged
- Claim: Held, unchanged
- Priority: Carried, unchanged
- WIP: Still counts against Backlog

## Event 6: Claim Released in Same Column

The claiming actor releases the claim in the same column.
Someone else can claim it again.

- State: Backlog, example, unchanged
- Claim: Released, no actor holds it. The ticket is now
  unclaimed.
- Priority: Carried, unchanged
- WIP: Still counts against Backlog

## Event 7: Ticket Moved to Wait State

When work in a state is finished, the ticket moves into
the wait state for the next state. The claiming actor
moves it. Claim ends on the move.

- State: Wait state for the next state, example, changed
  from Backlog
- Claim: Ended on the move, no actor holds it
- Priority: Carried, unchanged
- WIP: Now counts against the wait state, no longer
  against Backlog. The wait state has a WIP limit.

## Event 8: Ticket Moved Immediately, Capacity Available

When a ticket moves into a wait state, the system checks
the next state for available capacity. If there is
capacity, it moves into that column immediately.

In the AI world, if there is capacity in a column, then
there is an available worker by definition.

- State: Next state, example, changed from the wait state
- Claim: None, no actor holds it. The move claim, held
  by the downstream state, ended on the move.
- Priority: Carried, unchanged. The ticket takes its
  priority position in the new state by that key, not
  by arrival order.
- WIP: Now counts against the next state, no longer
  against the wait state

## Event 9: Ticket Waits, No Capacity

A ticket sits in a wait state only if the next state
does not have capacity. If there is no capacity, the
ticket just waits.

- State: Wait state, example, unchanged
- Claim: None, no actor holds it. No claim to move is
  made.
- Priority: Carried, unchanged
- WIP: Still counts against the wait state

## Event 10: Slot Opened in Next State

When the system sees a ticket move out of a state, it
knows capacity opened up. So it checks the previous
column for an available ticket to take that slot. That
is it.

- State: Next state, example, unchanged, now below its
  WIP limit, because a ticket moved out of it
- Claim: None, unchanged
- Action: The system pulls a ticket into the slot from
  the previous wait state, highest priority first, one
  per open slot, as in Event 11.

## Event 11: Ticket Moved by the System

The system moves the tickets in both cases, immediate
move if there is capacity, and pull from the wait state
when a slot opens. There is no claim to move it. The
system is the mover, not a human worker, and not a
downstream actor claiming it.

- State: Wait state, example, unchanged, until the move
- Claim: None, no claim to move is made
- Priority: Carried, unchanged
- WIP: Still counts against the wait state, until the move

## Event 12: Ticket Moved to Next State

The puller for the next state pulls the ticket, if its
state has capacity, below its WIP limit.

- State: Next state, example, changed from the wait state
- Claim: Ended on the move, no actor holds it
- Priority: Carried, unchanged. The ticket takes its
  priority position in the new state by that key, not
  by arrival order.
- WIP: Now counts against the next state, no longer
  against the wait state

## Event 13: Ticket Arrived in Next State

- State: Next state, example, changed from the wait state
- Claim: None, no actor holds it. No work has started
  in the new state yet.
- Priority: Carried, unchanged
- WIP: Now counts against the next state

The loop repeats from Event 3, claim, work, move to
wait, check capacity, move or wait, until Done.

## Event 14: Ticket Blocked

Blocked is an action for the claimant. They need to
unblock the ticket. It is part of the same work.

Block is invisible if there is no PM conversation and
reprioritization. No one cares if the worker who was
blocked also handles the blocker.

- State: Unchanged, the state the ticket was claimed in
- Claim: Held, unchanged. The claimant owns the unblock.
- Priority: Kept, unchanged, unless a PM conversation
  reprioritizes it
- WIP: Occupies WIP, unchanged. A blocked ticket
  occupies WIP and keeps its priority.

## Event 15: External Blocker, Product Manager Decides

If the blocker is external, out of the claimant's
control, it becomes a conversation. The product manager
decides whether the ticket keeps its priority.

- If it keeps its priority, there has to be active work
  to unblock it.
- If not, its priority is reduced, because the delay
  makes it lose its value.
- If the decision is to open up WIP, then discard the
  ticket, work with the external party to unblock, and
  then bring the work back into the backlog.

## Event 16: Ticket Unblocked

Blocker is only special when it leads to a conversation.
Then it changes into reprioritization or discard. So
there is no separate unblock event. Reprioritization is
Event 2. The event left is discard, Event 17.

- State: Unchanged, unless discarded
- Claim: Held, unchanged, unless the ticket was discarded
- Priority: Re-decided, if there was a conversation.
  Once it unblocks, there is another conversation about
  priority.
- WIP: Occupies WIP, unchanged, unless the ticket was
  discarded to open WIP.

## Event 17: Ticket Discarded to Open WIP

Discard is just a discard action. That is all. The
backend decides how that affects the ticket. From the
Workpull standpoint, the ticket leaves the system.
That is all.

- State: Discarded, no longer in a column
- Claim: Released, no actor holds it
- Priority: Not carried
- WIP: No longer counts against any state. WIP is opened.

## Done

Once a ticket moves into the Done column, it is done.
The system just closes Done tickets. Done is terminal.
There is no event in Done, no claim, no work, no wait,
no further move.
