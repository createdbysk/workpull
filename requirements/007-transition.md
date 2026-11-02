# Requirement 007 — Transition

## Requirement

A transition moves a ticket to the next state, only if
that state has capacity.

## Transition

- A transition moves a ticket to the next state.
- A transition happens only if the next state is below
  its WIP limit. If the next state is at its limit, the
  ticket stays, shown yellow, in its current state.
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
