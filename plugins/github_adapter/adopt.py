#!/usr/bin/env python3
"""Live GitHub adapter hook: adopt.

Brings one GitHub issue into Workpull: appends the
per-ticket record to the issue body and applies the
first state's label.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_adopt

if __name__ == "__main__":
    exit_code, output = run_adopt(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
