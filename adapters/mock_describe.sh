#!/usr/bin/env bash
# Mock describe hook for the trivial system: Backlog -> Done.
cat <<'EOF'
states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
EOF
