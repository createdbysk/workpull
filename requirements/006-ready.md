# Requirement 006 — Wait states

## Requirement

There are no colors and no signals on a ticket. A ticket
has a state, a claim, and a priority, and nothing else.
Readiness to move is a state, not a color.

## Wait states

- When work in a state is finished, the ticket moves
  into the wait state for the next state.
- A wait state is a separate state, not a color on a
  ticket in a work state. On a physical board, a wait
  state is a separate column.
- A wait state has a WIP limit, like any non-terminal
  state. That limit is provided by describe, in
  wip_limits.
- A ticket in a wait state is ready to move, and is what
  the system looks for when a slot comes open in the
  next state.
- A ticket in a wait state whose next state is at its
  WIP limit stays in the wait state, and still counts
  against the wait state's WIP limit.
- When a ticket moves from a wait state to the next
  state, its claim ended on the move, so no actor holds
  it, and no work has started in the new state yet.
  A ticket in a new state is claimable.

## Claim and work, without colors

- A ticket in a column gets claimed. Claim is a mutex.
  The worker who claimed it can do what they want with
  the ticket.
- When they release the claim in the same column,
  someone else can claim it again.
- Claim itself does not move a ticket, and does not
  change the ticket's state. It only gives the claiming
  actor exclusive access to act on that ticket.
