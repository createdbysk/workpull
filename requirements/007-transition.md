# Requirement 007 — Transition

## Requirement

A transition moves a ticket to the next state, only if
that state has capacity.

## Transition

- A transition moves a ticket to the next state.
- A transition happens when a slot comes open in the next
  state, and the next state is below its WIP limit, as in
  requirement 004. The system moves a ticket from the
  wait state for the next state. If the next state is at
  its limit, the ticket stays in the wait state.
- WIP limits are provided by describe, for each
  non-terminal state. Terminal states are not listed
  in wip_limits; they are unlimited by definition.
- Done is infinite. Done is not a working state, it is
  proof of doneness. In reality it could be just trash,
  except humans want that proof. A ticket closes at Done,
  so there can be no limit to the number of closed
  tickets, unless a system is built that trashes Done
  tickets. A transition into Done is never blocked by
  capacity.
- A state that looks like an endpoint is not Done if it
  still has work after it. Such a last working state
  still has a WIP limit, and its tickets then move to
  Done, where they close.
