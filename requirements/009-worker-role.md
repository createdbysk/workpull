# Requirement 009 — Worker role

## Requirement

A worker's role gives the right to work in a state, and
to mark a ticket green in that state. The system moves
tickets, not the worker; the role decides who can mark
ready, the system decides the move.

## Role

- A role gives a worker the right to mark a ticket green
  in the states that role covers.
- A specialist role covers one state only. For example,
  only a product manager can work in Backlog, and mark a
  Backlog ticket green.
- A generalist role covers more than one state. For
  example, a generalist can develop and review, and mark
  tickets green in both states.
- A ticket marked green by a worker without the role for
  that state is not a green ticket for pull.
