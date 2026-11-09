"""Tests for workpull adopt, through Click's runner."""

import os
from pathlib import Path
from typing import TypedDict

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli


class TicketOutcome(TypedDict, total=False):
    exit_code: int
    ticket_id: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(ticket_id: str, hook_command: Callable[[str], str]) -> str:
    hook = Path("mock_adopt.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_adopt.py")


def adopt_outcome(result: Result) -> TicketOutcome:
    outcome: TicketOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_adopt(runner: CliRunner):
    def _run(ticket: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("ADOPT_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_TICKET": ticket}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["adopt", ticket],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_adopt_happy_path(run_adopt, ticket_id: str) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    env = dict(os.environ)
    env["ADOPT_HOOK"] = "fake-hook"
    result = run_adopt("ticket-1", env, HookResult(0, f"{ticket_id}\n", ""))
    # THEN
    assert result.exception is None
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_real_hook(runner, isolated_filesystem, hook_command) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1", hook_command)
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hook
        result = runner.invoke(cli, ["adopt", "ticket-1"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_missing_hook(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env.pop("ADOPT_HOOK", None)
    result = run_adopt("ticket-1", env, HookResult(0, "ticket-1\n", ""))
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_failing_hook(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["ADOPT_HOOK"] = "fake-hook"
    result = run_adopt("ticket-1", env, HookResult(3, "", ""))
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_empty_ticket_id(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["ADOPT_HOOK"] = "fake-hook"
    result = run_adopt("ticket-1", env, HookResult(0, "", ""))
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_help(runner, normalize_help) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli adopt [OPTIONS] TICKET

            Adopt a ticket.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["adopt", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
