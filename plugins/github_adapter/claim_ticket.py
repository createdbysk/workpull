#!/usr/bin/env python3
"""Live GitHub adapter hook: claim-ticket.

Claims the highest priority unclaimed ticket in work
in a state and returns its id and claim token.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_claim_ticket

if __name__ == "__main__":
    exit_code, output = run_claim_ticket(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
