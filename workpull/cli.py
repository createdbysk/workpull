"""workpull CLI: describe.

Run a hook command from the environment, validate its TOML
output, print a normalized view. It knows no backend.

What this code guarantees, and what it does not:
- Hook commands are parsed with shlex.split and run with no shell.
- Context is passed only through environment variables, never
  interpolated into a command string.
- Hook output is parsed as TOML and schema-validated, never
  evaluated or executed.
- Hook commands come only from operator-set environment, never
  from backend output.
- Hooks are operator-trusted code. They inherit the operator's
  environment, and printed output must still be treated as
  untrusted text by the consumer. This code does not make
  backend text safe to follow as instructions.
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
    """Validate a parsed describe document. Returns an error string or None.

    Contract, for hook authors:
    - states: non-empty list, unique, each name letters, digits,
      space, hyphen, or underscore only, with no leading or
      trailing whitespace, and not whitespace-only. Slash, colon,
      dot, and other characters are not allowed.
    - claim: table mapping a state to a later state in the states
      list, by list position. A self-loop, or a target at or
      before the source, is rejected. An empty claim table is
      allowed, and means every state is terminal.
    """
    if not isinstance(view, dict):
        return "describe output is not a TOML document"
    if set(view) != {"states", "claim"}:
        return "describe output must contain exactly states and claim"
    states = view["states"]
    claim = view["claim"]
    if not isinstance(states, list) or not states:
        return "states must be a non-empty list"
    if len(states) != len(set(states)):
        return "states must be unique"
    for state in states:
        if (
            not isinstance(state, str)
            or not _STATE_NAME.match(state)
            or state != state.strip()
            or not state.strip()
        ):
            return f"invalid state name: {state!r}"
    if not isinstance(claim, dict):
        return "claim must be a table"
    order = {state: index for index, state in enumerate(states)}
    for source, target in claim.items():
        if source not in order:
            return f"claim source not in states: {source!r}"
        if target not in order:
            return f"claim target not in states: {target!r}"
        if order[target] <= order[source]:
            return f"claim target must be later than source: {source!r} -> {target!r}"
    return None


def format_describe(view):
    """Render a validated view in normalized TOML, no raw hook text.

    State names are validated to letters, digits, space, hyphen,
    and underscore only, so double-quoting them needs no escaping.
    """
    quoted = ", ".join(f'"{state}"' for state in view["states"])
    lines = [f"states = [{quoted}]", ""]
    lines.append("[claim]")
    for source in view["states"]:
        if source in view["claim"]:
            lines.append(f'{source} = "{view["claim"][source]}"')
    return "\n".join(lines)


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
    print(format_describe(view))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["describe"]:
        return describe()
    if argv in (["--help"], ["-h"]):
        print("usage: python -m workpull describe")
        print("       python -m workpull --version")
        print()
        print("Only describe is available.")
        return 0
    if argv == ["--version"]:
        print("workpull 0.1.0")
        return 0
    print("usage: python -m workpull describe", file=sys.stderr)
    print("       python -m workpull --help", file=sys.stderr)
    return 2
