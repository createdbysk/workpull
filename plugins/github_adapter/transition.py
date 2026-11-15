#!/usr/bin/env python3
"""Live GitHub adapter hook: transition.

Puts a claimed ticket into wait for the to-state and
ends the claim, when the presented token matches.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_transition

if __name__ == "__main__":
    exit_code, output = run_transition(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
