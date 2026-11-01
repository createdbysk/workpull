#!/usr/bin/env python3
"""GitHub issues describe mock.

Prints the generic view of GitHub issues as TOML, to validate
the shape of the describe contract. GitHub's issue states are
schema, not data, so this needs no network call, no token, and
no issue listing, and it is not a live backend adapter.

States: Open, Closed. Claim: Open -> Closed. Closed is terminal.
"""

print('states = ["Open", "Closed"]')
print()
print("[claim]")
print('Open = "Closed"')
