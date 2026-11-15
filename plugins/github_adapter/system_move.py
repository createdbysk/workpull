#!/usr/bin/env python3
"""Live GitHub adapter hook: system-move.

Completes a move: replaces a waiting ticket's state
label with the to-state's label and clears its
waiting-for record. No token; the system is the mover.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_system_move

if __name__ == "__main__":
    exit_code, output = run_system_move(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
