"""Tests for workpull adopt, through Click's runner."""

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
    help_text: str
    ticket_id: str | None


def write_mock_hook(ticket_id: str) -> str:
    """Write a mock adopt hook in the current directory."""
    hook = Path("mock_adopt.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_adopt.py")


def adopt_outcome(result) -> Outcome:
    """Outcome for an adopt run, with a ticket id only on success."""
    outcome: Outcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_adopt(runner: CliRunner):
    def _run(ticket: str, env: dict[str, str], obj: dict):
        return runner.invoke(cli, ["adopt", ticket], env=env, obj=obj)
    return _run


def test_adopt_happy_path(run_adopt) -> None:
    # GIVEN
    expected: Outcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1")
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hook
        result = run_adopt("ticket-1", env, {})
    # THEN
    assert result.exception is None
    actual: Outcome = adopt_outcome(result)
    assert expected == actual


def test_adopt_help(runner, normalize_help) -> None:
    # GIVEN
    expected: Outcome = {
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
    actual: Outcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
