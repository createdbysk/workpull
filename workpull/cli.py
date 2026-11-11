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
from typing import Callable, NamedTuple


class HookResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


RunHook = Callable[[str, dict[str, str]], HookResult]

_STATE_NAME = re.compile(r"^[A-Za-z0-9 _-]+$")


def run_hook(
    hook_command: str, env: dict[str, str]
) -> HookResult:
    """Run a hook command, no shell. Returns a HookResult.

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
        return HookResult(2, "", f"invalid hook command: {exc}\n")
    if not args:
        return HookResult(2, "", "empty hook command\n")
    hook_env = dict(os.environ)
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
        return HookResult(2, "", f"hook failed to run: {exc}\n")
    return HookResult(result.returncode, result.stdout, result.stderr)


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
    - wip_limits: table with exactly one entry per state.
      Each entry is an inline table with exactly work and
      wait, each a positive integer, or inf for unlimited.
      There is no other constraint on the values: the
      backend decides them, for every state.
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
    if set(wip_limits) != set(states):
        return "wip_limits must contain exactly one entry per state"
    for state, limits in wip_limits.items():
        if not isinstance(limits, dict):
            return f"invalid wip_limits: {state!r} -> {limits!r}"
        if set(limits) != {"work", "wait"}:
            return f"wip_limits for {state!r} must contain exactly work and wait"
        for field, limit in limits.items():
            if isinstance(limit, bool):
                return f"invalid wip_limit: {state!r} -> {field} {limit!r}"
            if isinstance(limit, float):
                if limit != float("inf"):
                    return f"invalid wip_limit: {state!r} -> {field} {limit!r}"
            elif not isinstance(limit, int) or limit < 1:
                return f"invalid wip_limit: {state!r} -> {field} {limit!r}"
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
        limits = view["wip_limits"][state]
        work = "inf" if limits["work"] == float("inf") else str(limits["work"])
        wait = "inf" if limits["wait"] == float("inf") else str(limits["wait"])
        lines.append(f'"{state}" = {{work = {work}, wait = {wait}}}')
    return "\n".join(lines)


def claim_ticket(state: str, run_hook_fn: RunHook) -> None:
    """Claim a single ticket in a state."""
    hook = os.environ.get("CLAIM_TICKET_HOOK")
    if not hook:
        click.echo("CLAIM_TICKET_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_STATE": state})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    try:
        claim = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(f"claim-ticket hook output is not valid TOML: {exc}", err=True)
        raise click.exceptions.Exit(2)
    if (
        not isinstance(claim, dict)
        or set(claim) != {"ticket", "token"}
        or not isinstance(claim["ticket"], str)
        or not claim["ticket"]
        or not isinstance(claim["token"], str)
        or not claim["token"]
    ):
        click.echo(
            "invalid claim-ticket output: expected ticket and token", err=True
        )
        raise click.exceptions.Exit(2)
    click.echo(result.stdout.strip())


def describe(run_hook_fn: RunHook) -> None:
    """Describe a backend's states and transitions."""
    hook = os.environ.get("DESCRIBE_HOOK")
    if not hook:
        click.echo("DESCRIBE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {})
    if result.returncode != 0:
        if result.stderr:
            click.echo(result.stderr, err=True, nl=False)
        else:
            click.echo("describe hook failed", err=True)
        raise click.exceptions.Exit(result.returncode or 1)
    try:
        view = tomllib.loads(result.stdout)
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


@click.group()
@click.version_option("0.1.0", prog_name="workpull")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Workpull: describe a backend's states and transitions.

    Composition root: this is where the real run_hook is
    wired in. A caller that already supplied a run_hook,
    in ctx.obj, keeps it, so tests can inject a fake.
    """
    if ctx.obj is None:
        empty_obj: dict[str, RunHook] = {}
        ctx.obj = empty_obj
    ctx.obj.setdefault("run_hook", run_hook)


def adopt(ticket: str, run_hook_fn: RunHook) -> None:
    """Adopt a ticket."""
    hook = os.environ.get("ADOPT_HOOK")
    if not hook:
        click.echo("ADOPT_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_TICKET": ticket})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    ticket_id = result.stdout.strip()
    if not ticket_id:
        click.echo("adopt hook returned no ticket id", err=True)
        raise click.exceptions.Exit(2)
    click.echo(ticket_id)


def prioritize(ticket: str, after: str, run_hook_fn: RunHook) -> None:
    """Move a ticket to a new priority."""
    hook = os.environ.get("PRIORITIZE_HOOK")
    if not hook:
        click.echo("PRIORITIZE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_TICKET": ticket, "WORKPULL_AFTER": after})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    ticket_id = result.stdout.strip()
    if not ticket_id:
        click.echo("prioritize hook returned no ticket id", err=True)
        raise click.exceptions.Exit(2)
    click.echo(ticket_id)


def release(ticket: str, token: str, run_hook_fn: RunHook) -> None:
    """Release a ticket's claim."""
    hook = os.environ.get("RELEASE_HOOK")
    if not hook:
        click.echo("RELEASE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_TICKET": ticket, "WORKPULL_TOKEN": token})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    ticket_id = result.stdout.strip()
    if not ticket_id:
        click.echo("release hook returned no ticket id", err=True)
        raise click.exceptions.Exit(2)
    click.echo(ticket_id)


def validate_count(counts: object) -> str | None:
    """Validate a parsed count document. Returns an error string or None.

    Contract, for hook authors: exactly wait and work,
    each a non-negative integer.
    """
    if (
        not isinstance(counts, dict)
        or set(counts) != {"wait", "work"}
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
    ):
        return "invalid count output: expected wait and work counts"
    return None


def count(state: str, run_hook_fn: RunHook) -> None:
    """Count tickets in a state."""
    hook = os.environ.get("COUNT_HOOK")
    if not hook:
        click.echo("COUNT_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_STATE": state})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    try:
        counts = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(f"count hook output is not valid TOML: {exc}", err=True)
        raise click.exceptions.Exit(2)
    error = validate_count(counts)
    if error:
        click.echo(error, err=True)
        raise click.exceptions.Exit(2)
    click.echo(result.stdout.strip())


def get_state(ticket: str, run_hook_fn: RunHook) -> None:
    """Get a ticket's current state."""
    hook = os.environ.get("GET_STATE_HOOK")
    if not hook:
        click.echo("GET_STATE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_TICKET": ticket})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    state = result.stdout.strip()
    if not state:
        click.echo("get-state hook returned no state", err=True)
        raise click.exceptions.Exit(2)
    click.echo(state)


def _fetch_current_state(ticket: str, run_hook_fn: RunHook) -> str:
    hook = os.environ.get("GET_STATE_HOOK")
    if not hook:
        click.echo("GET_STATE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_TICKET": ticket})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    state = result.stdout.strip()
    if not state:
        click.echo("get-state hook returned no state", err=True)
        raise click.exceptions.Exit(2)
    return state


def _fetch_describe_view(run_hook_fn: RunHook) -> dict[str, Any]:
    hook = os.environ.get("DESCRIBE_HOOK")
    if not hook:
        click.echo("DESCRIBE_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    try:
        view = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(f"describe hook output is not valid TOML: {exc}", err=True)
        raise click.exceptions.Exit(2)
    error = validate_describe(view)
    if error:
        click.echo(f"invalid describe output: {error}", err=True)
        raise click.exceptions.Exit(2)
    return view


class StateCounts(NamedTuple):
    wait: int
    work: int


class TransitionCheck(NamedTuple):
    allowed: bool
    view: dict[str, Any]
    work_count: int
    current_state: str


def _fetch_counts(to_state: str, run_hook_fn: RunHook) -> StateCounts:
    hook = os.environ.get("COUNT_HOOK")
    if not hook:
        click.echo("COUNT_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(hook, {"WORKPULL_STATE": to_state})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    try:
        counts = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(f"count hook output is not valid TOML: {exc}", err=True)
        raise click.exceptions.Exit(2)
    error = validate_count(counts)
    if error:
        click.echo(error, err=True)
        raise click.exceptions.Exit(2)
    return StateCounts(wait=counts["wait"], work=counts["work"])


def _check_transition(ticket: str, to_state: str, run_hook_fn: RunHook) -> TransitionCheck:
    current_state = _fetch_current_state(ticket, run_hook_fn)
    view = _fetch_describe_view(run_hook_fn)
    if to_state not in view["wip_limits"]:
        return TransitionCheck(
            allowed=False, view=view, work_count=0, current_state=current_state
        )
    counts = _fetch_counts(to_state, run_hook_fn)
    reachable = view["transitions"].get(current_state) == to_state
    wait_limit = view["wip_limits"][to_state]["wait"]
    return TransitionCheck(
        allowed=reachable and counts.wait < wait_limit,
        view=view,
        work_count=counts.work,
        current_state=current_state,
    )


def can_transition(ticket: str, to_state: str, run_hook_fn: RunHook) -> None:
    """Check whether a ticket can move to a state."""
    check = _check_transition(ticket, to_state, run_hook_fn)
    click.echo("true" if check.allowed else "false")


def _move_ticket_immediately_if_capacity(
    ticket: str,
    to_state: str,
    work_count: int,
    work_limit: int | float,
    run_hook_fn: RunHook,
) -> None:
    if work_count < work_limit:
        hook = os.environ.get("SYSTEM_MOVE_HOOK")
        if not hook:
            click.echo("SYSTEM_MOVE_HOOK is not set", err=True)
            raise click.exceptions.Exit(2)
        result = run_hook_fn(
            hook, {"WORKPULL_TICKET": ticket, "WORKPULL_TO_STATE": to_state}
        )
        if result.returncode != 0:
            raise click.exceptions.Exit(result.returncode)
        if not result.stdout.strip():
            click.echo("system move hook returned no ticket id", err=True)
            raise click.exceptions.Exit(2)


def validate_list_waiting(waiting: dict[str, Any]) -> str | None:
    """Validate a parsed list-waiting document. Returns an error string or None.

    Contract, for hook authors: exactly tickets, a list of
    non-empty strings, in priority order, first is highest.
    The document is always a dict: tomllib.loads returns a
    dict for every input, so no non-dict check is needed.
    """
    if (
        set(waiting) != {"tickets"}
        or not isinstance(waiting["tickets"], list)
        or any(
            not isinstance(ticket, str) or not ticket
            for ticket in waiting["tickets"]
        )
    ):
        return "invalid list-waiting output: expected tickets"
    return None


def _fetch_waiting_tickets(state: str, run_hook_fn: RunHook) -> list[str]:
    # Caller guarantees LIST_WAITING_HOOK is set: an unset
    # hook means Event 10 is not configured, and the pull
    # is skipped before this is called.
    hook = os.environ["LIST_WAITING_HOOK"]
    result = run_hook_fn(hook, {"WORKPULL_STATE": state})
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    try:
        waiting = tomllib.loads(result.stdout)
    except tomllib.TOMLDecodeError as exc:
        click.echo(f"list-waiting hook output is not valid TOML: {exc}", err=True)
        raise click.exceptions.Exit(2)
    error = validate_list_waiting(waiting)
    if error:
        click.echo(error, err=True)
        raise click.exceptions.Exit(2)
    return waiting["tickets"]


def _pull_one_waiting_ticket_into_opened_slot(
    old_state: str, view: dict[str, Any], run_hook_fn: RunHook
) -> None:
    # No list hook means no pull is attempted, so a transition
    # without Event 10 configured keeps its old behaviour.
    if not os.environ.get("LIST_WAITING_HOOK"):
        return
    counts = _fetch_counts(old_state, run_hook_fn)
    work_limit = view["wip_limits"][old_state]["work"]
    if not counts.work < work_limit:
        return
    waiting = _fetch_waiting_tickets(old_state, run_hook_fn)
    if not waiting:
        return
    _move_ticket_immediately_if_capacity(
        waiting[0], old_state, counts.work, work_limit, run_hook_fn
    )


def transition(ticket: str, to_state: str, token: str, run_hook_fn: RunHook) -> None:
    """Move a ticket to a wait state."""
    check = _check_transition(ticket, to_state, run_hook_fn)
    if not check.allowed:
        click.echo("transition is not allowed", err=True)
        raise click.exceptions.Exit(2)
    hook = os.environ.get("TRANSITION_HOOK")
    if not hook:
        click.echo("TRANSITION_HOOK is not set", err=True)
        raise click.exceptions.Exit(2)
    result = run_hook_fn(
        hook,
        {
            "WORKPULL_TICKET": ticket,
            "WORKPULL_TO_STATE": to_state,
            "WORKPULL_TOKEN": token,
        },
    )
    if result.returncode != 0:
        raise click.exceptions.Exit(result.returncode)
    ticket_id = result.stdout.strip()
    if not ticket_id:
        click.echo("transition hook returned no ticket id", err=True)
        raise click.exceptions.Exit(2)
    _move_ticket_immediately_if_capacity(
        ticket_id,
        to_state,
        check.work_count,
        check.view["wip_limits"][to_state]["work"],
        run_hook_fn,
    )
    _pull_one_waiting_ticket_into_opened_slot(
        check.current_state, check.view, run_hook_fn
    )
    click.echo(ticket_id)


@cli.command(name="adopt")
@click.argument("ticket")
@click.pass_context
def adopt_command(ctx: click.Context, ticket: str) -> None:
    """Adopt a ticket."""
    adopt(ticket, ctx.obj["run_hook"])


@cli.command(name="claim-ticket")
@click.argument("state")
@click.pass_context
def claim_ticket_command(ctx: click.Context, state: str) -> None:
    """Claim a single ticket in a state."""
    claim_ticket(state, ctx.obj["run_hook"])


@cli.command(name="prioritize")
@click.argument("ticket")
@click.argument("after")
@click.pass_context
def prioritize_command(ctx: click.Context, ticket: str, after: str) -> None:
    """Move a ticket to a new priority."""
    prioritize(ticket, after, ctx.obj["run_hook"])


@cli.command(name="release")
@click.argument("ticket")
@click.argument("token")
@click.pass_context
def release_command(ctx: click.Context, ticket: str, token: str) -> None:
    """Release a ticket's claim."""
    release(ticket, token, ctx.obj["run_hook"])


@cli.command(name="count")
@click.argument("state")
@click.pass_context
def count_command(ctx: click.Context, state: str) -> None:
    """Count tickets in a state."""
    count(state, ctx.obj["run_hook"])


@cli.command(name="get-state")
@click.argument("ticket")
@click.pass_context
def get_state_command(ctx: click.Context, ticket: str) -> None:
    """Get a ticket's current state."""
    get_state(ticket, ctx.obj["run_hook"])


@cli.command(name="can-transition")
@click.argument("ticket")
@click.argument("to_state")
@click.pass_context
def can_transition_command(ctx: click.Context, ticket: str, to_state: str) -> None:
    """Check whether a ticket can move to a state."""
    can_transition(ticket, to_state, ctx.obj["run_hook"])


@cli.command(name="transition")
@click.argument("ticket")
@click.argument("to_state")
@click.argument("token")
@click.pass_context
def transition_command(ctx: click.Context, ticket: str, to_state: str, token: str) -> None:
    """Move a ticket to a wait state."""
    transition(ticket, to_state, token, ctx.obj["run_hook"])


@cli.command(name="describe")
@click.pass_context
def describe_command(ctx: click.Context) -> None:
    """Describe a backend's states and transitions."""
    describe(ctx.obj["run_hook"])
