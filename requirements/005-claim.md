# Requirement 005 — Claim

## Requirement

Claim is a mutex. Claim gives an actor the ability to
change the color of a ticket. That is it.

## Claim

- Claim gives an actor exclusive access to act on a ticket.
- Claim gives that actor, and only that actor, the ability
  to change the ticket's color: yellow for on work, green
  for ready to move, red for blocked.
- Claim itself does not move a ticket, does not change
  the ticket's state, and does not change its color. It
  only gives the claiming actor the ability to do so.
- While a ticket is claimed, no other actor can change
  its color.
- A claim ends when the ticket moves to the next state,
  when the actor releases it, or when the actor is gone.
  The mutex is then released.
