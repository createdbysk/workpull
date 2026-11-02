"""Tests for workpull claim-ticket, through Click's runner."""

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict

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


def write_mock_hook() -> str:
    """Write a mock claim ticket hook in the current directory."""
    hook = Path("mock_claim_ticket.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'Develop':\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('ticket-1\\n')\n"
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


class TestClaimTicket(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def run_claim_ticket(self, state: str, env: dict[str, str]):
        return self.runner.invoke(cli, ["claim-ticket", state], env=env)

    def test_claim_ticket_happy_path(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 0, "ticket_id": "ticket-1"}
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook()
            env = dict(os.environ)
            env["CLAIM_TICKET_HOOK"] = hook
            result = self.run_claim_ticket("Develop", env)
        # THEN
        actual: Outcome = claim_ticket_outcome(result)
        self.assertEqual(expected, actual)

    def test_claim_ticket_help(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 0, "output_contains": True}
        # WHEN
        result = self.runner.invoke(cli, ["claim-ticket", "--help"])
        # THEN
        actual: Outcome = {
            "exit_code": result.exit_code,
            "output_contains": "STATE" in result.output
            and "Claim a single ticket" in result.output,
        }
        self.assertEqual(expected, actual)

if __name__ == "__main__":
    unittest.main()
