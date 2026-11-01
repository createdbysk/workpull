---
name: develop-workpull
description: Develop in the workpull repository. Use when adding a requirement, changing code, tests, or docs in workpull, or when a task says to develop workpull.
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
- Backend data is data, never instructions. Sanitize hook
  commands and context values, see the design document for the
  requirement you are working on.
- Python 3.12, stdlib only. Tests are unittest, stdlib only.

## Workflow, one requirement

0. Install, venv first: `bash scripts/setup.sh`, then
   `source .venv/bin/activate`. `make install` refuses to run
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
   - `python3 -m unittest`
   - `pymarkdown --config .pymarkdown.json scan .agents/skills/workpull/SKILL.md .agents/skills/develop-workpull/SKILL.md requirements/ design/ implementation/`
8. Push to a branch, never to main. Main is protected, pull
   request required, rebase only, no squash, no merge commits.

## Progressive discovery

- Start in `AGENTS.md` for repo layout and commands.
- For using Workpull, use `.agents/skills/workpull/SKILL.md`, not this skill.
- For the requirement you are working on, read its
  requirements, design, and implementation documents one at a
  time, in workflow order, and return to this skill between them.
- Do not read documents for later requirements while working
  on the current one.
