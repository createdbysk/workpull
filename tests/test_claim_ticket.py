"""Tests for workpull claim-ticket, through Click's runner."""

import os
import sys
from pathlib import Path
from typing import TypedDict

import pytest
from click.testing import CliRunner

from tests.helpers import hook_command, isolated_filesystem
from workpull.cli import HookResult, cli


class Outcome(TypedDict, total=False):
    exit_code: int
    output_contains: bool
    ticket_id: str | None
    help_text: str


def write_mock_hook(ticket_id: str) -> str:
    """Write a mock claim ticket hook in the current directory."""
    hook = Path("mock_claim_ticket.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'Develop':\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_claim_ticket.py")


def claim_ticket_outcome(result) -> Outcome:
    """Outcome for a claim ticket run, with a ticket id only on success."""
    outcome: Outcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome



@pytest.fixture
def run_claim_ticket(runner: CliRunner):
    def _run(state: str, env: dict[str, str], obj: dict):
        return runner.invoke(cli, ["claim-ticket", state], env=env, obj=obj)
    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])

def test_claim_ticket_happy_path(run_claim_ticket, ticket_id: str) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(ticket_id)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook
        result = run_claim_ticket("Develop", env, {})
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_injected_run_hook(run_claim_ticket) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = "fake-hook"
        result = run_claim_ticket("Develop", env, obj={"run_hook": lambda hook, env: HookResult(0, "ticket-1\n", "")})
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual


def test_missing_hook(run_claim_ticket) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        env = dict(os.environ)
        env.pop("CLAIM_TICKET_HOOK", None)
        result = run_claim_ticket("Develop", env, {})
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_failing_hook(run_claim_ticket) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("failing.py")
        hook.write_text("import sys\nsys.exit(3)\n")
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook_command("failing.py")
        result = run_claim_ticket("Develop", env, {})
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_empty_ticket_id(run_claim_ticket) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("empty.py")
        hook.write_text("pass\n")
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook_command("empty.py")
        result = run_claim_ticket("Develop", env, {})
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_claim_ticket_help(runner, normalize_help) -> None:
    # GIVEN
    expected: Outcome = {
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
    actual: Outcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual

