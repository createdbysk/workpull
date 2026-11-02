# Requirement 004 — Pull

## Requirement

Work is pulled by a state, not by a worker. A state pulls
work from the state before it only when it has capacity.
Stop starting, start finishing. The goal is to get work
done, not to start work.

This requirement supersedes the claim transition in
requirement 001: claim no longer moves a ticket.

## Claim

- Claim gives a worker exclusive access to act on a ticket.
- Claim does not change the ticket's state.
- While a ticket is claimed, no other worker acts on it.
- A claim ends when the ticket moves to the next state,
  when the worker releases it, or when the worker is gone.

## Ready

- When the work in a state is finished, the worker marks
  the ticket ready.
- A ready ticket is shown yellow. Yellow is a signal, not
  a state: the ticket's state does not change.
- A ready ticket whose transition is blocked stays in its
  current state, shown yellow, and still counts against
  that state's WIP limit.

## Transition

- A transition moves a ticket to the next state.
- A transition happens only if the next state is below
  its WIP limit. If the next state is at its limit, the
  ticket stays, shown yellow, in its current state.
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

## Pull

- When a state has capacity, it pulls from the state
  before it.
- It pulls the highest priority ready ticket from that
  state, not the ticket that finished first.
- A ready lower priority ticket moves when a higher
  priority ticket is not ready. Capacity does not sit
  idle waiting for unfinished work.

## Priority

- Within a column, priority is top to bottom.
- Priority is usually set at backlog refinement and
  carried till done.
- If business priority changes, a column is
  reprioritized mid flight, and the new order is
  carried forward from there.
- A ticket entering a column takes its priority position
  in that column. A higher priority ticket entering
  later goes above a lower priority ticket already
  there. It does not displace it.
- Across columns, work closer to done gets attention
  before work farther from done, even if the farther
  work had the higher original priority. A blocked
  ticket closer to done is helped before new work
  farther from done is started.
