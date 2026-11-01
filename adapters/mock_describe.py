#!/usr/bin/env python3
"""Mock describe hook for the trivial system: Backlog -> Done.

Prints the generic view as TOML. Used in examples and as a
reference for the describe contract, not as a backend.
"""

print('states = ["Backlog", "Done"]')
print()
print("[claim]")
print('Backlog = "Done"')
