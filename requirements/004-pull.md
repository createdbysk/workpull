# Requirement 004 — Pull

## Requirement

Work is pulled by a state, not by a worker. A state pulls
work from the state before it only when it has capacity.
Stop starting, start finishing. The goal is to get work
done, not to start work.

## Pull

- When a state has capacity, it pulls from the state
  before it.
- It pulls the highest priority ready ticket from that
  state, not the ticket that finished first.
- A ready lower priority ticket moves when a higher
  priority ticket is not ready. Capacity does not sit
  idle waiting for unfinished work.
