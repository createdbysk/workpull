#!/usr/bin/env python3
"""Live GitHub adapter hook: count.

Counts a state's tickets: work from the state labels,
wait from the per-ticket records.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_count

if __name__ == "__main__":
    exit_code, output = run_count(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
