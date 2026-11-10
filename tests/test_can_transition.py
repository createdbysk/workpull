"""Tests for workpull can-transition, through Click's runner."""

import os
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunCanTransition = Callable[
    [str, str, dict[str, str], HookResult, HookResult, HookResult], Result
]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class CanTransitionOutcome(TypedDict, total=False):
    exit_code: int
    output: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


class CanTransitionCase(NamedTuple):
    case_name: str
    current_state: str
    to_state: str
    wait_count: int
    expected_output: str


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


def write_mock_get_state_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_get_state.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('Backlog\\n')\n"
    )
    return hook_command("mock_get_state.py")


def write_mock_describe_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_describe.py")
    hook.write_text(
        "import os, sys\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(" + repr(DESCRIBE_VIEW) + ")\n"
    )
    return hook_command("mock_describe.py")


def write_mock_count_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_count.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'In Progress':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('wait = 1\\nwork = 3\\n')\n"
    )
    return hook_command("mock_count.py")


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


def _case_id(case: CanTransitionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        CanTransitionCase(
            case_name="true",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            expected_output="true",
        ),
        CanTransitionCase(
            case_name="false_unreachable",
            current_state="Backlog",
            to_state="In Work",
            wait_count=1,
            expected_output="false",
        ),
        CanTransitionCase(
            case_name="false_at_limit",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=2,
            expected_output="false",
        ),
        CanTransitionCase(
            case_name="true_inf_wait_limit",
            current_state="In Progress",
            to_state="Done",
            wait_count=99,
            expected_output="true",
        ),
    ],
    ids=_case_id,
)
def test_can_transition(
    run_can_transition: RunCanTransition, case: CanTransitionCase
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {
        "exit_code": 0,
        "output": case.expected_output,
    }
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        case.to_state,
        env,
        HookResult(0, f"{case.current_state}\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, f"wait = {case.wait_count}\nwork = 3\n", ""),
    )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_missing_get_state_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env.pop("GET_STATE_HOOK", None)
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
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_missing_describe_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env.pop("DESCRIBE_HOOK", None)
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
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_missing_count_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env.pop("COUNT_HOOK", None)
    result = run_can_transition(
        "ticket-1",
        "In Progress",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_failing_get_state_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 3, "output": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "In Progress",
        env,
        HookResult(3, "", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_failing_describe_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 3, "output": None}
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
        HookResult(3, "", ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_failing_count_hook(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 3, "output": None}
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
        HookResult(3, "", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_invalid_describe_toml(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
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
        HookResult(0, "wait = \n", ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_invalid_count_toml(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
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
        HookResult(0, "wait = \n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_invalid_describe_output(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
    invalid_view = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Backlog"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "Done",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, invalid_view, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_empty_state(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    result = run_can_transition(
        "ticket-1",
        "In Progress",
        env,
        HookResult(0, "", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_unknown_to_state_is_false(
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
        "Unknown",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
    )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 0, "output": "true"}
    # WHEN
    with isolated_filesystem():
        get_state_hook = write_mock_get_state_hook(hook_command)
        describe_hook = write_mock_describe_hook(hook_command)
        count_hook = write_mock_count_hook(hook_command)
        env = dict(os.environ)
        env["GET_STATE_HOOK"] = get_state_hook
        env["DESCRIBE_HOOK"] = describe_hook
        env["COUNT_HOOK"] = count_hook
        result = runner.invoke(
            cli, ["can-transition", "ticket-1", "In Progress"], env=env, obj={}
        )
    # THEN
    assert result.exception is None
    actual: CanTransitionOutcome = can_transition_outcome(result)
    assert expected == actual


def test_can_transition_invalid_count_output(
    run_can_transition: RunCanTransition,
) -> None:
    # GIVEN
    expected: CanTransitionOutcome = {"exit_code": 2, "output": None}
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
        HookResult(0, "work = 3\n", ""),
    )
    # THEN
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
