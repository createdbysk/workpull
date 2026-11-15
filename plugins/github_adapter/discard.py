#!/usr/bin/env python3
"""Live GitHub adapter hook: discard.

Removes a ticket's per-ticket record and state label
together, when the presented token matches the claim.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_discard

if __name__ == "__main__":
    exit_code, output = run_discard(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
