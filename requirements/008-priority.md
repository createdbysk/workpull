# Requirement 008 — Priority

## Requirement

Priority orders work, within a column and across columns.
The goal is to get work done, not to start work.

## Priority value

- Priority is a fractional order key carried with the
  ticket, set by a prioritization step and carried till
  done. The prioritization step assigns priority values
  to tickets such that the values stay unique. That is
  all. There is no column claim.
- Prioritization itself has a long mutex. Tell the system
  begin prioritization. Only then you are allowed to
  change the values. Then say end prioritization, and
  the values lock.
- Prioritize as a move between tickets. A ticket is moved
  above or below another ticket, to the top, or up or
  down one step. The user never types a fractional value.
  The system computes the midpoint key.
- The catch is the race. The system can error if there
  is a conflict. It is a low occurrence race.
- An order key lives in a dense order: between any two
  keys there is always another key, so an insert never
  has to renumber the other tickets.
- A ticket inserted between two tickets takes the
  midpoint key between theirs. A ticket inserted after
  the last ticket takes a key after the last key. The
  exact value is any key strictly between its neighbours,
  or after the last key if there is no next key.
- Order keys are stored as strings or arbitrary-precision
  decimals, never as floats. A float cannot represent
  .1, .15, or .91 exactly, and midpoint calculations
  lose precision after many inserts.
- When keys get too long, the column is rebalanced once,
  back to short keys, for example .1, .2, .3, top to
  bottom. Rebalancing is rare, and is the only operation
  that changes other tickets' keys.
- Reprioritizing a ticket means giving it a new order
  key at its new position, by the midpoint rule above.

## Priority within a column

- Within a column, priority is top to bottom, by fractional
  value, smallest first.
- Priority is usually set at backlog refinement and
  carried till done.
- If business priority changes, a column is
  reprioritized mid flight, and the new order is
  carried forward from there.
- A ticket entering a column takes its priority position
  in that column. A higher priority ticket entering
  later goes above a lower priority ticket already
  there. It does not displace it.

## Priority across columns

- Across columns, work closer to done gets attention
  before work farther from done, even if the farther
  work had the higher original priority. A blocked
  ticket closer to done is helped before new work
  farther from done is started.
- A claimed ticket is not preempted. If a lower value
  ticket is claimed, whoever claimed it continues to
  work on it, even if a higher value ticket waits.
  For example, a claimed ticket worth 10 continues,
  even if a ticket worth 100 waits.
- If the claimed ticket blocks, then it waits, and the
  higher value ticket is pulled, if there is capacity
  in that column.
- If the column has capacity and the claimed ticket is
  not blocked, then the higher value ticket moves into
  the higher spot, and someone else with capacity takes
  it.
