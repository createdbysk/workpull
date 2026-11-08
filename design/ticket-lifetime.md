# Ticket lifetime — event storming

DDD event storming, one event at a time. Domain events are
in the past tense, in the ubiquitous language of
requirements 004 to 008: state, signal, claim, pull, WIP
limit. A signal is not a state. Claim is a mutex, not a
move. Signals are white unclaimed, green ready, yellow on
work, red blocked.

## Event 1: Ticket Originated in Backlog

- State: Backlog
- Signal: White, unclaimed
- Claim: None, no actor holds it
- WIP: Backlog is unbounded, WIP limit inf, so entry never
  waits for a slot

A ticket originates in Backlog. There is no earlier event.

## Event 2: Backlog Prioritized

Gap found by event storming: a ticket cannot be claimed
from Backlog until Backlog has been prioritized.

- State: Backlog, unchanged
- Signal: White, unchanged
- Claim: None, no actor holds it
- Priority: Set at backlog refinement, top to bottom, as
  a fractional order key carried with the ticket. A
  ticket inserted between two tickets takes the midpoint
  key between theirs. A ticket inserted after the last
  ticket takes a key after the last key. Order keys are
  stored as strings or arbitrary-precision decimals,
  never as floats. When keys get too long, the column is
  rebalanced once, back to short keys. The ticket carries
  that key until Done, unless a business priority change
  reprioritizes it mid-flight, giving it a new order key.

## Event 3: Ticket Claimed

- State: Backlog, unchanged
- Signal: White, unchanged, claim does not change the
  signal
- Claim: Held, by the actor who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, and returned it to that actor.
- WIP: Still counts against Backlog
