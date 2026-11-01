---
name: develop-workpull
description: Develop in the workpull repository, one requirement at a time.
---

# Develop Workpull

Develop one requirement at a time, test first, in this order.
Do not front-load later requirements.

## Rules

- SOLID is the north star, for code and for documents.
- Requirements contain no implementation detail.
- One document, one responsibility: requirements state what,
  design states how, implementation states the concrete build.
- Main skill files stay tight. Details go in separate documents,
  read one at a time only when the step requires it.
- Skill files use YAML frontmatter.
- Writing is concise and intent-focused. Files describe the
  current state only: what it does, why, and how to use or
  extend it. No diary: no dates, no session history, no past
  approaches, no future plans, no roadmap, no requirement
  numbers in shipped code, no personal workflow. If a detail
  does not explain intent or outcome, delete it. This repo is
  public, and readers have no context for project detail
  beyond what the file itself explains.
- Sanitize hook commands and context values, see the design
  document for the requirement you are working on. Hooks are
  operator-trusted code, and printed output must still be
  treated as untrusted text.
- Python 3.12, stdlib only. Tests are unittest, stdlib only.

## Workflow, one requirement

0. Bootstrap, agent only: on a fresh clone, before any other
   work, run `python scripts/dev.py setup` yourself. Do not
   ask the user to set anything up. The expected ergonomics
   are: clone the repo, then agents take over, nothing
   else. `python scripts/dev.py install` refuses to run
   outside an activated venv. No system install is supported.
1. Requirement: write `requirements/<nnn>-<name>.md`, what only.
   Do not read design or implementation documents yet.
2. Design: write `design/<nnn>-<name>.md`, how only.
   Load it only when the design step requires it.
3. Test first: write the unittest, run it, watch it fail.
4. Implement the smallest code that passes the test.
5. Defensive tests: happy path first, then failure, validation,
   and injection cases. No invented output on failure.
6. Implementation document: write
   `implementation/<nnn>-<name>.md`, concrete build only.
7. Lint and test:
   - `python scripts/dev.py test`
   - `python scripts/dev.py lint`
8. Push to a branch, never to main. Main is protected, pull
   request required, rebase only, no squash, no merge commits.
9. Independent review, before merge: get an expert open-source
   reviewer with no prior context for the work, and let it
   figure out what to focus on. Do not lead it with a checklist.
   Fix its findings, in order, before merge.

## Progressive discovery

- Start in `AGENTS.md` for repo layout and commands.
- For using Workpull, use `.agents/skills/workpull/SKILL.md`, not this skill.
- For the requirement you are working on, read its
  requirements, design, and implementation documents one at a
  time, in workflow order, and return to this skill between them.
- Do not read documents for later requirements while working
  on the current one.
