"""workpull CLI: describe and claim-ticket.

Run a hook command from the environment, validate its TOML
output, print a normalized view. Claim a single ticket in
a state, printing the ticket id the hook returns. It knows
no backend.

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
from typing import Any

import click

_STATE_NAME = re.compile(r"^[A-Za-z0-9 _-]+$")


def run_hook(
    hook_command: str, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Run a hook command, no shell. Returns (returncode, stdout, stderr).

    The hook command is in canonical POSIX form, on every
    platform: POSIX quoting, forward slashes for paths. It is
    parsed once with POSIX shlex, to a list, and that list is
    passed to subprocess, which converts it to the platform
    form. There is no platform branch here.
    The hook is killed after 30 seconds, and that timeout is
    reported only as a generic hook failure.
    """
    try:
        args = shlex.split(hook_command, posix=True)
    except ValueError as exc:
        return 2, "", f"invalid hook command: {exc}\n"
    if not args:
        return 2, "", "empty hook command\n"
    hook_env = dict(os.environ)
    if env:
        hook_env.update(env)
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            env=hook_env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, "", f"hook failed to run: {exc}\n"
    return result.returncode, result.stdout, result.stderr


def validate_describe(view: object) -> str | None:
    """Validate a parsed describe document. Returns an error string or None.

    Contract, for hook authors:
    - states: non-empty list, unique, each name letters, digits,
      space, hyphen, or underscore only, with no leading or
      trailing whitespace, and not whitespace-only. Slash, colon,
      dot, and other characters are not allowed.
    - transitions: table mapping a state to a later state in the states
      list, by list position. A self-loop, or a target at or
      before the source, is rejected. An empty transitions table is
      allowed, and means every state is terminal.
    - wip_limits: table with exactly one entry per non-terminal
      state, and no entry for a terminal state. Each value is
      a positive integer, or inf for unlimited. Terminal states
      are unlimited by definition, and are not listed.
    """
    if not isinstance(view, dict):
        return "describe output is not a TOML document"
    if set(view) != {"states", "transitions", "wip_limits"}:
        return "describe output must contain exactly states, transitions, and wip_limits"
    states = view["states"]
    transitions = view["transitions"]
    if not isinstance(states, list) or not states:
        return "states must be a non-empty list"
    for state in states:
        if not isinstance(state, str):
            return f"invalid state name: {state!r}"
    if len(states) != len(set(states)):
        return "states must be unique"
    for state in states:
        if (
            not _STATE_NAME.match(state)
            or state != state.strip()
            or not state.strip()
        ):
            return f"invalid state name: {state!r}"
    if not isinstance(transitions, dict):
        return "transitions must be a table"
    order = {state: index for index, state in enumerate(states)}
    for source, target in transitions.items():
        if not isinstance(source, str) or not isinstance(target, str):
            return f"invalid transition: {source!r} -> {target!r}"
        if source not in order:
            return f"transition source not in states: {source!r}"
        if target not in order:
            return f"transition target not in states: {target!r}"
        if order[target] <= order[source]:
            return f"transition target must be later than source: {source!r} -> {target!r}"
    wip_limits = view["wip_limits"]
    if not isinstance(wip_limits, dict):
        return "wip_limits must be a table"
    non_terminal = set(transitions)
    terminal = set(states) - non_terminal
    if set(wip_limits) & terminal:
        return "terminal state must not be in wip_limits"
    if set(wip_limits) != non_terminal:
        return "wip_limits must contain exactly one entry per non-terminal state"
    for state, limit in wip_limits.items():
        if isinstance(limit, bool):
            return f"invalid wip_limit: {state!r} -> {limit!r}"
        if isinstance(limit, float):
            if limit != float("inf"):
                return f"invalid wip_limit: {state!r} -> {limit!r}"
        elif not isinstance(limit, int) or limit < 1:
            return f"invalid wip_limit: {state!r} -> {limit!r}"
    return None


def format_describe(view: dict[str, Any]) -> str:
    """Render a validated view in normalized TOML, no raw hook text.

    State names are validated to letters, digits, space, hyphen,
    and underscore only, so double-quoting them needs no escaping.
    """
    quoted = ", ".join(f'"{state}"' for state in view["states"])
    lines = [f"states = [{quoted}]", ""]
    lines.append("[transitions]")
    for source in view["states"]:
        if source in view["transitions"]:
            lines.append(f'"{source}" = "{view["transitions"][source]}"')
    lines.append("")
    lines.append("[wip_limits]")
    for state in view["states"]:
        if state in view["transitions"]:
            limit = view["wip_limits"][state]
            value = "inf" if limit == float("inf") else str(limit)
            lines.append(f'"{state}" = {value}')
    return "\n".join(lines)


@click.group()
@click.version_option("0.1.0", prog_name="workpull")
def cli() -> None:
    """Workpull: describe a backend's states and transitions."""


@cli.command()
@click.argument("state")
def claim_ticket(state: str) -> None:
    """Claim a single ticket in a state."""
    hook = os.environ.get("CLAIM_TICKET_HOOK")
    if not hook:
        click.echo("CLAIM_TICKET_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    _, stdout, _ = run_hook(hook, env={"WORKPULL_STATE": state})
    click.echo(stdout.strip())


@cli.command()
def describe() -> None:
    """Describe a backend's states and transitions."""
    hook = os.environ.get("DESCRIBE_HOOK")
    if not hook:
        click.echo("DESCRIBE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    returncode, stdout, stderr = run_hook(hook)
    if returncode != 0:
        if stderr:
            click.echo(stderr, err=True, nl=False)
        else:
            click.echo("describe hook failed", err=True)
        raise click.exceptions.Exit(returncode or 1)
    try:
        view = tomllib.loads(stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(
            f"describe hook output is not valid TOML: {exc}", err=True
        )
        raise click.exceptions.Exit(2)
    error = validate_describe(view)
    if error:
        click.echo(f"invalid describe output: {error}", err=True)
        raise click.exceptions.Exit(2)
    click.echo(format_describe(view))


def main(argv: list[str] | None = None) -> int:
    """Entry point for `python -m workpull`.

    With no arguments, this is the real entry point, and Click
    handles exit codes itself. With arguments, this is a
    programmatic call, and the Click exit code is returned.
    """
    if argv is None:
        cli()
        return 0
    try:
        result = cli.main(args=argv, prog_name="workpull", standalone_mode=False)
    except click.exceptions.Exit as exc:
        return exc.exit_code
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    return result if isinstance(result, int) else 0
