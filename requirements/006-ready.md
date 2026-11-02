# Requirement 006 — Ready

## Requirement

Signals show the state of work on a ticket. A signal is
not a state: the ticket's state does not change when its
signal changes.

## Signals

- Green means ready to move. When the work in a state is
  finished, the worker marks the ticket green.
- Yellow means on work. Work in progress is shown yellow.
  A yellow ticket is not ready to move.
- Red means blocked. A red ticket is not ready to move.

## Ready

- A green ticket is ready to move, and is what the system
  looks for when a slot comes open in the next state.
- A green ticket whose transition is blocked by the next
  state's WIP limit stays in its current state, shown
  green, and still counts against that state's WIP limit.
- Only a worker with the role for that state can mark a
  ticket green in that state; see requirement 009.
