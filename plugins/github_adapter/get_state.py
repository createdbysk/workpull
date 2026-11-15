#!/usr/bin/env python3
"""Live GitHub adapter hook: get-state.

Prints a ticket's state: the waiting-for state while
it waits, otherwise the state on its label.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_get_state

if __name__ == "__main__":
    exit_code, output = run_get_state(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
