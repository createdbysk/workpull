"""Tests for workpull prioritize, through Click's runner."""

import os
from pathlib import Path
from typing import TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunPrioritize = Callable[[str, str, dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class TicketOutcome(TypedDict, total=False):
    exit_code: int
    ticket_id: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(ticket_id: str, after: str, hook_command: HookCommand) -> str:
    hook = Path("mock_prioritize.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        f"if os.environ.get('WORKPULL_AFTER') != '{after}':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET', 'WORKPULL_AFTER'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_prioritize.py")


def prioritize_outcome(result: Result) -> TicketOutcome:
    outcome: TicketOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_prioritize(runner: CliRunner) -> RunPrioritize:
    def _run(ticket: str, after: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("PRIORITIZE_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_TICKET": ticket, "WORKPULL_AFTER": after}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["prioritize", ticket, after],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_prioritize_happy_path(run_prioritize: RunPrioritize, ticket_id: str) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    env = dict(os.environ)
    env["PRIORITIZE_HOOK"] = "fake-hook"
    result = run_prioritize(
        "ticket-1", "ticket-2", env, HookResult(0, f"{ticket_id}\n", "")
    )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_top(run_prioritize: RunPrioritize) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    env = dict(os.environ)
    env["PRIORITIZE_HOOK"] = "fake-hook"
    result = run_prioritize(
        "ticket-1", "WORKPULL_TOP", env, HookResult(0, "ticket-1\n", "")
    )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1", "ticket-2", hook_command)
        env = dict(os.environ)
        env["PRIORITIZE_HOOK"] = hook
        result = runner.invoke(
            cli, ["prioritize", "ticket-1", "ticket-2"], env=env, obj={}
        )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_missing_hook(run_prioritize: RunPrioritize) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env.pop("PRIORITIZE_HOOK", None)
    result = run_prioritize(
        "ticket-1", "ticket-2", env, HookResult(0, "ticket-1\n", "")
    )
    # THEN
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_failing_hook(run_prioritize: RunPrioritize) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["PRIORITIZE_HOOK"] = "fake-hook"
    result = run_prioritize("ticket-1", "ticket-2", env, HookResult(3, "", ""))
    # THEN
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_empty_ticket_id(run_prioritize: RunPrioritize) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["PRIORITIZE_HOOK"] = "fake-hook"
    result = run_prioritize("ticket-1", "ticket-2", env, HookResult(0, "", ""))
    # THEN
    actual: TicketOutcome = prioritize_outcome(result)
    assert expected == actual


def test_prioritize_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli prioritize [OPTIONS] TICKET AFTER

            Move a ticket to a new priority.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["prioritize", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
