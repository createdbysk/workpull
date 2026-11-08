"""Tests for workpull adopt, through Click's runner."""

import os
from pathlib import Path
from typing import TypedDict

import pytest
from click.testing import CliRunner, Result

from tests.helpers import hook_command, isolated_filesystem
from workpull.cli import HookResult, cli


class TicketOutcome(TypedDict, total=False):
    exit_code: int
    ticket_id: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(ticket_id: str) -> str:
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
    def _run(ticket: str, env: dict[str, str], obj: dict) -> Result:
        return runner.invoke(cli, ["adopt", ticket], env=env, obj=obj)
    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_adopt_happy_path(run_adopt, ticket_id: str) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(ticket_id)
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hook
        result = run_adopt("ticket-1", env, {})
    # THEN
    assert result.exception is None
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_injected_run_hook(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        env = dict(os.environ)
        env["ADOPT_HOOK"] = "fake-hook"
        result = run_adopt("ticket-1", env, obj={"run_hook": lambda hook, env: HookResult(0, "ticket-1\n", "")})
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_missing_hook(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        env = dict(os.environ)
        env.pop("ADOPT_HOOK", None)
        result = run_adopt("ticket-1", env, {})
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_failing_hook(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("failing.py")
        hook.write_text("import sys\nsys.exit(3)\n")
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hook_command("failing.py")
        result = run_adopt("ticket-1", env, {})
    # THEN
    actual: TicketOutcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_empty_ticket_id(run_adopt) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("empty.py")
        hook.write_text("pass\n")
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hook_command("empty.py")
        result = run_adopt("ticket-1", env, {})
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
