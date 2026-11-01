"""workpull CLI, requirement 001: describe.

Single responsibility: run a hook command from the environment,
validate its TOML output, print it. It knows no backend.

Sanitization, by design:
- Hook commands are parsed with shlex.split and run with no shell.
- Context is passed only through environment variables, never
  interpolated into a command string.
- Hook output is parsed as TOML and schema-validated, never
  evaluated or executed. Backend text is data, never instructions.
- Hook commands come only from operator-set environment, never
  from backend output.
"""

import os
import re
import shlex
import subprocess
import sys
import tomllib

_STATE_NAME = re.compile(r"^[A-Za-z0-9 _-]+$")


def run_hook(hook_command):
    """Run a hook command, no shell. Returns (returncode, stdout, stderr)."""
    try:
        args = shlex.split(hook_command)
    except ValueError as exc:
        return 2, "", f"invalid hook command: {exc}\n"
    if not args:
        return 2, "", "empty hook command\n"
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(os.environ),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", f"hook failed to run: {exc}\n"
    return result.returncode, result.stdout, result.stderr


def validate_describe(view):
    """Validate a parsed describe document. Returns an error string or None."""
    if not isinstance(view, dict):
        return "describe output is not a TOML document"
    if set(view) != {"states", "claim"}:
        return "describe output must contain exactly states and claim"
    states = view["states"]
    claim = view["claim"]
    if not isinstance(states, list) or not states:
        return "states must be a non-empty list"
    for state in states:
        if not isinstance(state, str) or not _STATE_NAME.match(state):
            return f"invalid state name: {state!r}"
    if not isinstance(claim, dict):
        return "claim must be a table"
    for source, target in claim.items():
        if source not in states:
            return f"claim source not in states: {source!r}"
        if target not in states:
            return f"claim target not in states: {target!r}"
    return None


def describe():
    """Implement `workpull describe`. Returns an exit code."""
    hook = os.environ.get("DESCRIBE_HOOK")
    if not hook:
        print("DESCRIBE_HOOK is not set", file=sys.stderr)
        return 2
    returncode, stdout, stderr = run_hook(hook)
    if returncode != 0:
        if stderr:
            print(stderr, file=sys.stderr, end="")
        else:
            print("describe hook failed", file=sys.stderr)
        return returncode or 1
    try:
        view = tomllib.loads(stdout)
    except tomllib.TOMLDecodeError as exc:
        print(f"describe hook output is not valid TOML: {exc}", file=sys.stderr)
        return 2
    error = validate_describe(view)
    if error:
        print(f"invalid describe output: {error}", file=sys.stderr)
        return 2
    print(stdout.rstrip("\n"))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["describe"]:
        return describe()
    print("usage: python -m workpull describe", file=sys.stderr)
    return 2
