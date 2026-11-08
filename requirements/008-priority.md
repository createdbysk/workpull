# Requirement 008 — Priority

## Requirement

Priority orders work, within a column and across columns.
The goal is to get work done, not to start work.

## Priority value

- Priority is a fractional order key carried with the
  ticket, set at backlog refinement and carried till done.
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
