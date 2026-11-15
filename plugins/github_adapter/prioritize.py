#!/usr/bin/env python3
"""Live GitHub adapter hook: prioritize.

Moves one ticket to just after the anchor ticket, or
to the top, by rewriting its fractional order key.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_prioritize

if __name__ == "__main__":
    exit_code, output = run_prioritize(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
