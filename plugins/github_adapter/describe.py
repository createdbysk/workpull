#!/usr/bin/env python3
"""Live GitHub adapter hook: describe.

Prints the workpull.toml configuration of the target
repository, read through the GitHub layer.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from plugins.github_adapter.github_backend import run_describe

if __name__ == "__main__":
    exit_code, output = run_describe(os.environ)
    sys.stdout.write(output)
    sys.exit(exit_code)
