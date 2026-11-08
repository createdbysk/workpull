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
  a fractional value carried with the ticket. A column
  starts with .1, .2, .3. A ticket inserted between two
  tickets takes a value between theirs, adding decimal
  places as needed. The ticket carries that value until
  Done, unless a business priority change reprioritizes
  it mid-flight, giving it a new fractional value.

## Event 3: Ticket Claimed

- State: Backlog, unchanged
- Signal: White, unchanged, claim does not change the
  signal
- Claim: Held, by the actor who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, and returned it to that actor.
- WIP: Still counts against Backlog
