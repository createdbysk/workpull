# Requirement 008 — Priority

## Requirement

Priority orders work, within a column and across columns.
The goal is to get work done, not to start work.

## Priority value

- Priority is a fractional value carried with the ticket,
  set at backlog refinement and carried till done.
- A column starts with values .1, .2, .3, top to bottom.
- A ticket inserted between two tickets takes a value
  between theirs, adding decimal places as needed, for
  example .15 between .1 and .2. No other ticket's value
  changes on an insert, so there is no renumbering churn.
- Reprioritizing a ticket means giving it a new fractional
  value at its new position.

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
