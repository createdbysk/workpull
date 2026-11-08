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

## Event 2: Ticket Claimed

- State: Backlog, unchanged
- Signal: White, unchanged, claim does not change the
  signal
- Claim: Held, by the actor who called
  `claim-ticket Backlog`. The system picked the top
  unclaimed ticket, and returned it to that actor.
- WIP: Still counts against Backlog
