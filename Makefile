.PHONY: venv install test lint

# Create the venv and install workpull with dev deps.
venv:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

# Install only inside an activated venv. Refuses system installs.
install:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "error: activate a venv first: source .venv/bin/activate" >&2; \
		echo "or run: bash scripts/setup.sh" >&2; \
		exit 1; \
	fi
	pip install -e ".[dev]"

test:
	python3 -m unittest

lint:
	pymarkdown --config .pymarkdown.json scan .agents/skills/workpull/SKILL.md .agents/skills/develop-workpull/SKILL.md requirements/ design/ implementation/
