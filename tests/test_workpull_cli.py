"""Tests for the workpull CLI itself, through Click's runner.

This file owns the top level help test. When a command is
added, update the expected command list here, not in the
command's own test file.
"""

from typing import TypedDict

from click.testing import CliRunner

from workpull.cli import cli


class Outcome(TypedDict):
    exit_code: int
    has_all_commands: bool


def test_top_level_help_lists_commands() -> None:
    # GIVEN
    commands = ["claim-ticket", "describe"]
    expected: Outcome = {"exit_code": 0, "has_all_commands": True}
    # WHEN
    result = CliRunner().invoke(cli, ["--help"])
    # THEN
    actual: Outcome = {
        "exit_code": result.exit_code,
        "has_all_commands": all(command in result.output for command in commands),
    }
    assert expected == actual


