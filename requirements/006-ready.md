# Requirement 006 — Ready

## Requirement

Finished work is marked ready, shown yellow. Yellow is
a signal, not a state.

## Ready

- When the work in a state is finished, the worker marks
  the ticket ready.
- A ready ticket is shown yellow. Yellow is a signal, not
  a state: the ticket's state does not change.
- A ready ticket whose transition is blocked stays in its
  current state, shown yellow, and still counts against
  that state's WIP limit.
