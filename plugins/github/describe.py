#!/usr/bin/env python3
"""GitHub issues describe adapter.

Prints the generic view of GitHub issues as TOML. GitHub's issue
states are schema, not data, so this needs no network call, no
token, and no issue listing.

States: Open, Closed. Claim: Open -> Closed. Closed is terminal.
"""

print('states = ["Open", "Closed"]')
print()
print("[claim]")
print('Open = "Closed"')
