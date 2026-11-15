#!/usr/bin/env python3
"""Live GitHub adapter hook: release.

Ends a ticket's claim when the presented token matches
the stored claim.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_release

if __name__ == "__main__":
    exit_code, output = run_release(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
