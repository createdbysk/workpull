"""Tests for workpull can-transition, through Click's runner."""

import os
from typing import TypedDict

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunCanTransition = Callable[
    [str, str, dict[str, str], HookResult, HookResult, HookResult], Result
]
NormalizeHelp = Callable[[str], str]


class CanTransitionOutcome(TypedDict, total=False):
    exit_code: int
    output: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


DESCRIBE_VIEW = """states = ["Backlog", "In Progress", "In Work", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
"In Work" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""


def can_transition_outcome(result: Result) -> CanTransitionOutcome:
    outcome: CanTransitionOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["output"] = result.output.strip()
    else:
        outcome["output"] = None
    return outcome


@pytest.fixture
def run_can_transition(runner: CliRunner) -> RunCanTransition:
    def _run(
        ticket: str,
        to_state: str,
        env: dict[str, str],
        get_state_result: HookResult,
        describe_result: HookResult,
        count_result: HookResult,
    ) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook == env.get("GET_STATE_HOOK"):
                if hook_env != {"WORKPULL_TICKET": ticket}:
                    return HookResult(1, "", "")
                return get_state_result
            if hook == env.get("DESCRIBE_HOOK"):
                if hook_env != {}:
                    return HookResult(1, "", "")
                return describe_result
            if hook == env.get("COUNT_HOOK"):
                if hook_env != {"WORKPULL_STATE": to_state}:
                    return HookResult(1, "", "")
                return count_result
            return HookResult(1, "", "")

        return runner.invoke(
            cli,
            ["can-transition", ticket, to_state],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


def test_can_transition_happy_path(run_can_transition: RunCanTransition) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 0, "output": "true"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "In Progress",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_unreachable_is_false(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 0, "output": "false"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "In Work",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_wait_at_limit_is_false(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 0, "output": "false"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "In Progress",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 2\nwork = 3\n", ""),
    )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli can-transition [OPTIONS] TICKET TO_STATE

            Check whether a ticket can move to a state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["can-transition", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
