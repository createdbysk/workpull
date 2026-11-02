# Requirement 005 — Claim

## Requirement

Claim gives a worker exclusive access to a ticket. Claim
does not move a ticket. This supersedes the old claim
transition in requirement 001, which has been corrected
to a transition.

## Claim

- Claim gives a worker exclusive access to act on a ticket.
- Claim does not change the ticket's state.
- While a ticket is claimed, no other worker acts on it.
- A claim ends when the ticket moves to the next state,
  when the worker releases it, or when the worker is gone.
