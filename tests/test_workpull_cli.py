"""Tests for the workpull CLI itself, through Click's runner.

This file owns the top level help test. When a command is
added, update the expected command list here, not in the
command's own test file.
"""

from typing import TypedDict

from workpull.cli import cli


class Outcome(TypedDict):
    exit_code: int
    help_text: str


def test_top_level_help_lists_commands(runner, normalize_help) -> None:
    # GIVEN
    expected: Outcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli [OPTIONS] COMMAND [ARGS]...

            Workpull: describe a backend's states and transitions.

            Composition root: this is where the real run_hook is wired in. A caller that
            already supplied a run_hook, in ctx.obj, keeps it, so tests can inject a
            fake.

            Options:
              --version  Show the version and exit.
              --help     Show this message and exit.

            Commands:
              adopt         Adopt a ticket.
              claim-ticket  Claim a single ticket in a state.
              describe      Describe a backend's states and transitions.
              prioritize    Move a ticket in a state, to a new priority.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["--help"])
    # THEN
    actual: Outcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
