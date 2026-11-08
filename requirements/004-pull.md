# Requirement 004 — Pull

## Requirement

Work is pulled by a state, not by a worker. A state pulls
work from the state before it only when it has capacity.
Stop starting, start finishing. The goal is to get work
done, not to start work.

## Pull

- A slot comes open in a state when its count drops below
  its WIP limit, so it has capacity.
- When a slot comes open, the system looks for tickets
  in the wait state for it, and moves them.
- It moves the highest priority ticket from that wait
  state, not the ticket that finished first.
- A lower priority ticket in the wait state moves when a
  higher priority ticket is not in the wait state.
  Capacity does not sit idle waiting for unfinished work.
- If there is no ticket in the wait state, the slot stays
  open. It does not pull unfinished work, and it does
  not start new work.
