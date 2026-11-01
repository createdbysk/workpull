# Contributing

Work on a branch, never directly on main. Main is protected:
changes only via pull request, rebase only, no squash, no merge
commits.

Before a pull request:

```bash
python scripts/dev.py test
python scripts/dev.py lint
python scripts/dev.py type
```

A pull request also needs an independent review, by a reviewer
with no prior context for the work, before merge. That review
is a gate, not a courtesy check.

See `AGENTS.md` for the full workflow.
