"""Tests for workpull transition, through Click's runner."""

import os
from pathlib import Path
from typing import TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunTransition = Callable[[str, str, dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class TicketOutcome(TypedDict, total=False):
    exit_code: int
    ticket_id: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(ticket_id: str, to_state: str, hook_command: HookCommand) -> str:
    hook = Path("mock_transition.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        f"if os.environ.get('WORKPULL_TO_STATE') != '{to_state}':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET', 'WORKPULL_TO_STATE'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_transition.py")


def transition_outcome(result: Result) -> TicketOutcome:
    outcome: TicketOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_transition(runner: CliRunner) -> RunTransition:
    def _run(ticket: str, to_state: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("TRANSITION_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_TICKET": ticket, "WORKPULL_TO_STATE": to_state}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["transition", ticket, to_state],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_transition_happy_path(run_transition: RunTransition, ticket_id: str) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    env = dict(os.environ)
    env["TRANSITION_HOOK"] = "fake-hook"
    result = run_transition(
        "ticket-1", "In Progress", env, HookResult(0, f"{ticket_id}\n", "")
    )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1", "In Progress", hook_command)
        env = dict(os.environ)
        env["TRANSITION_HOOK"] = hook
        result = runner.invoke(
            cli, ["transition", "ticket-1", "In Progress"], env=env, obj={}
        )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_missing_hook(run_transition: RunTransition) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env.pop("TRANSITION_HOOK", None)
    result = run_transition("ticket-1", "In Progress", env, HookResult(0, "ticket-1\n", ""))
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_failing_hook(run_transition: RunTransition) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["TRANSITION_HOOK"] = "fake-hook"
    result = run_transition("ticket-1", "In Progress", env, HookResult(3, "", ""))
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_empty_ticket_id(run_transition: RunTransition) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["TRANSITION_HOOK"] = "fake-hook"
    result = run_transition("ticket-1", "In Progress", env, HookResult(0, "", ""))
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli transition [OPTIONS] TICKET TO_STATE

            Move a ticket to a wait state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["transition", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
