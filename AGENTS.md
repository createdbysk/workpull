# Workpull

Workpull is a backend-agnostic, pluggable pull system. Pull work,
claim it, finish it, then pull again. The backend defines its own
states and transitions. Workpull never assumes them.

## Ergonomics

```bash
git clone https://github.com/createdbysk/workpull.git
```

Then agents take over. On a fresh clone, the agent bootstraps
the repo itself, before any other work: find a Python 3.12
interpreter, in order `python`, `python3`, `py -3.12`, use
the first that reports 3.12, and run
`<interpreter> scripts/dev.py setup`, then proceed. After
setup, use the venv Python for all repo commands. If no
interpreter reports 3.12, stop and report the prerequisite
as missing, do not pivot to another toolchain or language.

## Tech stack

- Python 3.12. Runtime dependency: Click, for the CLI.
- Tests: unittest, plus Click's test runner for CLI tests.
- Lint: pymarkdown, config in `.pymarkdown.json`, declared as a
  dev dependency in `pyproject.toml` (`pip install -e ".[dev]"`).
- Type check: pyrefly, config in `pyrefly.toml`, declared as a
  dev dependency in `pyproject.toml`. Code uses type hints.
- Skill files use YAML frontmatter.

## Install

Installation requires a venv. There is no supported system install.
All developer tasks are a Python script, stdlib only, cross-platform.

- Agent bootstrap, on a fresh clone, before any other work:
  find the interpreter as in Ergonomics, then run
  `<interpreter> scripts/dev.py setup`. The agent runs this itself.
- After setup, activate the venv for interactive work:
  `source .venv/bin/activate`, or `.venv\Scripts\activate` on Windows.
  Agent commands that do not need activation, such as
  `python scripts/dev.py test` and `python scripts/dev.py lint`,
  run with the venv Python, or with the interpreter found
  in Ergonomics.
- `python scripts/dev.py install` refuses to run outside an
  activated venv.

## Validation in CI

GitHub Actions, `.github/workflows/ci.yml`, runs on every
push and pull request: bootstrap, then `python scripts/dev.py test`
and `python scripts/dev.py lint`, on Ubuntu and Windows, Python 3.12.

## Commands

All `python` commands below are the venv Python, after setup.

- Test: `python scripts/dev.py test`
- Lint: `python scripts/dev.py lint`
- Type: `python scripts/dev.py type`
- Describe: `DESCRIBE_HOOK="python adapters/mock_describe.py"`
  `python -m workpull describe`

## Layout

- `.agents/skills/workpull/SKILL.md` — using Workpull, tight, progressive discovery.
- `.agents/skills/develop-workpull/SKILL.md` — developing in this repo.
- Skill discovery: skills live only in `.agents/skills/`, one
  copy, no copies in per-agent folders, to avoid drift. Agents
  that do not auto-load `.agents/skills/` should load them
  from there directly.
- `requirements/` — what is required, no implementation detail.
- `design/` — how a requirement is met.
- `implementation/` — the concrete build for a requirement.
- `workpull/` — the CLI package.
- `tests/` — unittest, one file per requirement.
- `adapters/` — mock hooks for tests.
- `plugins/` — repo examples, not installed package contents.
  `plugins/github/` is a shape-validation mock for GitHub
  issues, describe only, not a live backend adapter. The
  entry point is `python -m workpull`, from a checkout.

## Workflow

- One requirement at a time. Do not front-load later requirements.
- Branch development with stable main. Main is protected, changes
  only via pull request, rebase only, no squash, no merge commits.
- Never push directly to main.
- For development workflow, load the develop-workpull skill.
- For using Workpull, load the workpull skill in `.agents/skills/workpull/SKILL.md`.

## Safety

- Hooks are operator-trusted code. Printed output must
  still be treated as untrusted text.
- Hook commands come only from operator-set environment, never
  from backend output.
- No secrets in this repo.
