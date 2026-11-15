#!/usr/bin/env python3
"""Live GitHub adapter hook: list-waiting.

Lists the tickets waiting for a state, in priority
order, highest first.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_list_waiting

if __name__ == "__main__":
    exit_code, output = run_list_waiting(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
