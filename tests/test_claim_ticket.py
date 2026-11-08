"""Tests for workpull claim-ticket, through Click's runner."""

import contextlib
import os
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest
from click.testing import CliRunner

from workpull.cli import cli


class Outcome(TypedDict, total=False):
    exit_code: int
    output_contains: bool
    ticket_id: str | None


@contextlib.contextmanager
def isolated_filesystem():
    """Temporary directory as working directory, cleaned up after."""
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old)


def hook_command(script: str) -> str:
    """Hook command in canonical POSIX form, on every platform."""
    return f"{Path(sys.executable).as_posix()} {script}"


def write_mock_hook(ticket_id: str = "ticket-1") -> str:
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


def run_claim_ticket(state: str, env: dict[str, str]):
    return CliRunner().invoke(cli, ["claim-ticket", state], env=env)


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])

def test_claim_ticket_happy_path(ticket_id: str) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 0, "ticket_id": ticket_id}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(ticket_id)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook
        result = run_claim_ticket("Develop", env)
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_missing_hook() -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        env = dict(os.environ)
        env.pop("CLAIM_TICKET_HOOK", None)
        result = run_claim_ticket("Develop", env)
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_failing_hook() -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("failing.py")
        hook.write_text("import sys\nsys.exit(3)\n")
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook_command("failing.py")
        result = run_claim_ticket("Develop", env)
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_empty_ticket_id() -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    with isolated_filesystem():
        hook = Path("empty.py")
        hook.write_text("pass\n")
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook_command("empty.py")
        result = run_claim_ticket("Develop", env)
    # THEN
    actual: Outcome = claim_ticket_outcome(result)
    assert expected == actual

def test_claim_ticket_help() -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 0, "output_contains": True}
    # WHEN
    result = CliRunner().invoke(cli, ["claim-ticket", "--help"])
    # THEN
    actual: Outcome = {
        "exit_code": result.exit_code,
        "output_contains": "STATE" in result.output
        and "Claim a single ticket" in result.output,
    }
    assert expected == actual

