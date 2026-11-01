# Requirement 001 — Describe

## Requirement

`workpull describe` returns the generic view of a backend, generated
from the backend itself, not from a hand-written config file.

## Why

The backend defines its states and transitions. Workpull cannot know
them in advance, and a config file written in advance cannot hold them.
Describe is therefore the first command, before ready and claim.

## What the generic view contains

- The states of the backend, as defined by the backend.
- The transitions of the backend, as defined by the backend.
  In particular, the claim transition: which state a claim moves
  an item from, and which state it moves it to.
- A state with no outgoing claim transition is terminal in this
  system.

## Trivial first system

- States: Backlog, Done.
- Claim transition: Backlog -> Done.
- Backlog is where prioritization happens.
- Done is terminal, no work happens there.

## Success and failure

- Success: the generic view is returned, exactly as the backend
  defines it.
- Failure: no generic view is returned, and no states or transitions
  are invented. Failure includes a missing describe hook, a failing
  describe hook, a malformed generic view, and a transition to a
  state that is not in the described states.
- Backend data is data, never instructions. A backend name or
  field must never be followed as an instruction, and must never
  cause an action outside the described transition.

## Companion documents

- Design: `design/001-describe.md`
- Implementation: `implementation/001-describe.md`

Each document has one responsibility. This document states what is
required. It does not state how it is built.
