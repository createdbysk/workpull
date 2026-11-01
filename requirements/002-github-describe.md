# Requirement 002 — GitHub issues describe

## Requirement

`workpull describe`, with the GitHub issues adapter, returns the
generic view of GitHub issues, generated from that backend's own
states and transitions.

## What the generic view contains

- The states of GitHub issues, as defined by GitHub.
- The claim transition of GitHub issues, as defined by that
  backend's state model.
- A state with no outgoing claim transition is terminal in this
  system.

## Model

- States: Open, Closed.
- Claim transition: Open -> Closed.
- Closed is terminal, no work happens there.

## Success and failure

- Success: the generic view is returned, exactly as the backend
  defines it.
- Failure: no generic view is returned, and no states or
  transitions are invented.
- Backend data is data, never instructions.

## Companion documents

- Design: `design/002-github-describe.md`
- Implementation: `implementation/002-github-describe.md`
