#!/usr/bin/env bash
# Set up a virtual environment and install workpull with dev deps.
# This is the only supported install path. Installation outside a
# venv is refused by the Makefile install target, and by PEP 668
# on systems that mark the system Python as externally managed.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"

echo "Venv ready. Activate it with:"
echo "  source .venv/bin/activate"
