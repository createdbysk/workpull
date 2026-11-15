# Requirement 006 — Ready — REJECTED, archived

Rejected 2026-11-08, by Satish, in event storming.
Colors / signals are rejected. A ticket has no color.
Readiness is a wait state, a separate state, not a signal
on a ticket in a work state. See requirement 006, Wait
states, for the replacement.

## Requirement

Signals show the state of work on a ticket. A signal is
not a state: the ticket's state does not change when its
signal changes.

## Signals

- White means unclaimed. When a ticket first moves into a
  state, it is shown white. No claim, no work started, not
  blocked, not ready. A white ticket is claimable.
- Green means ready to move. When the work in a state is
  finished, the worker marks the ticket green.
- Yellow means in work. Work in progress is shown yellow.
  A yellow ticket is not ready to move.
- Red means blocked. A red ticket is not ready to move.

## Ready

- A green ticket is ready to move, and is what the system
  looks for when a slot comes open in the next state.
- A green ticket whose transition is blocked by the next
  state's WIP limit stays in its current state, shown
  green, and still counts against that state's WIP limit.
- When a ticket moves to a new state, its signal resets to
  white. Its claim ended on the move, so no actor holds it,
  and no work has started in the new state yet.
- Claim itself does not change the signal. A claimed ticket
  stays white until the claiming actor marks it yellow, in
  work.
