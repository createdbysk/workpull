"""Tests for workpull claim-ticket, through Click's runner."""

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
    hook = Path("mock_claim_ticket.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'Develop':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_claim_ticket.py")


def claim_ticket_outcome(result: Result) -> TicketOutcome:
    outcome: TicketOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_claim_ticket(runner: CliRunner):
    def _run(state: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("CLAIM_TICKET_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_STATE": state}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["claim-ticket", state],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_claim_ticket_happy_path(run_claim_ticket, ticket_id: str) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket("Develop", env, HookResult(0, f"{ticket_id}\n", ""))
    # THEN
    assert result.exception is None
    actual: TicketOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_real_hook(runner, isolated_filesystem, hook_command) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1", hook_command)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook
        result = runner.invoke(cli, ["claim-ticket", "Develop"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: TicketOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_missing_hook(run_claim_ticket) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env.pop("CLAIM_TICKET_HOOK", None)
    result = run_claim_ticket("Develop", env, HookResult(0, "ticket-1\n", ""))
    # THEN
    actual: TicketOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_failing_hook(run_claim_ticket) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket("Develop", env, HookResult(3, "", ""))
    # THEN
    actual: TicketOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_empty_ticket_id(run_claim_ticket) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket("Develop", env, HookResult(0, "", ""))
    # THEN
    actual: TicketOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_help(runner, normalize_help) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli claim-ticket [OPTIONS] STATE

            Claim a single ticket in a state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["claim-ticket", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
