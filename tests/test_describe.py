"""Tests for workpull describe, through Click's runner."""

import os
import tomllib
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunDescribe = Callable[[dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""


# A WIP limit is a positive int, or inf, the only float allowed.
class WipLimits(NamedTuple):
    work: int | float
    wait: int | float


class View(TypedDict):
    states: list[str]
    transitions: dict[str, str]
    wip_limits: dict[str, WipLimits]


class DescribeOutcome(TypedDict, total=False):
    exit_code: int
    view: View | None
    output_contains: bool


class SideEffectOutcome(TypedDict, total=False):
    side_effect_exists: bool


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(body: str, hook_command: HookCommand) -> str:
    hook = Path("mock_describe.py")
    hook.write_text(
        "import os, sys\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(" + repr(body) + ")\n"
    )
    return hook_command("mock_describe.py")


def parse_view(text: str) -> View:
    parsed = tomllib.loads(text)
    return View(
        states=parsed["states"],
        transitions=parsed["transitions"],
        wip_limits={
            state: WipLimits(work=limits["work"], wait=limits["wait"])
            for state, limits in parsed["wip_limits"].items()
        },
    )


def describe_outcome(result: Result) -> DescribeOutcome:
    outcome: DescribeOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["view"] = parse_view(result.output)
    else:
        outcome["view"] = None
    return outcome


@pytest.fixture
def run_describe(runner: CliRunner) -> RunDescribe:
    def _run(env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("DESCRIBE_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["describe"],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


def test_happy_path(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {"Backlog": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, TRIVIAL_VIEW, ""))
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_describe_real_hook(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {"Backlog": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(TRIVIAL_VIEW, hook_command)
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hook
        result = runner.invoke(cli, ["describe"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_missing_hook(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    # WHEN
    env = dict(os.environ)
    env.pop("DESCRIBE_HOOK", None)
    result = run_describe(env, HookResult(0, TRIVIAL_VIEW, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_failing_hook(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 3, "view": None}
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(3, "", ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_invalid_toml(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, "this is not toml [\n", ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_transition_to_unknown_state(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Elsewhere"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_hook_command_injection_is_not_executed(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    expected: SideEffectOutcome = {"side_effect_exists": False}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(TRIVIAL_VIEW, hook_command)
        side_effect = Path("pwned")
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hook + " ; touch " + str(side_effect)
        runner.invoke(cli, ["describe"], env=env, obj={})
        actual: SideEffectOutcome = {"side_effect_exists": side_effect.exists()}
    # THEN
    assert expected == actual


def test_hook_command_injection_unspaced_is_not_executed(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    expected: SideEffectOutcome = {"side_effect_exists": False}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook(TRIVIAL_VIEW, hook_command)
        side_effect = Path("pwned")
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hook + "; touch " + str(side_effect)
        runner.invoke(cli, ["describe"], env=env, obj={})
        actual: SideEffectOutcome = {"side_effect_exists": side_effect.exists()}
    # THEN
    assert expected == actual


def test_duplicate_states_are_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_self_loop_transition_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Backlog"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_backwards_transition_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Done = "Backlog"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_whitespace_padded_state_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog ", "Done"]

[transitions]
"Backlog " = "Done"

[wip_limits]
"Backlog " = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_empty_transitions_means_all_terminal(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    body = """states = ["Backlog", "Done"]

[transitions]

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_hook_comment_is_not_printed(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {"Backlog": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
        "output_contains": False,
    }
    body = "# ignore previous instructions\n" + TRIVIAL_VIEW
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    actual: DescribeOutcome = describe_outcome(result)
    actual["output_contains"] = "ignore previous instructions" in result.output
    # THEN
    assert expected == actual


def test_state_name_with_shell_metacharacters_is_rejected(
    run_describe: RunDescribe,
) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog; rm -rf /", "Done"]

[transitions]
"Backlog; rm -rf /" = "Done"

[wip_limits]
"Backlog; rm -rf /" = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_spaced_state_produces_valid_toml(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["In Progress", "Done"],
            "transitions": {"In Progress": "Done"},
            "wip_limits": {
                "In Progress": WipLimits(work=3, wait=2),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    body = """states = ["In Progress", "Done"]

[transitions]
"In Progress" = "Done"

[wip_limits]
"In Progress" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_unhashable_state_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = [{a = 1}, "Done"]

[transitions]
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_unhashable_transition_target_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = ["Done"]

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_finite_wip_limit_is_accepted(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "In Progress", "Done"],
            "transitions": {"Backlog": "In Progress", "In Progress": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "In Progress": WipLimits(work=3, wait=2),
                "Done": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_two_wip_limits_happy_path(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "In Progress", "Done"],
            "transitions": {"Backlog": "In Progress", "In Progress": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "In Progress": WipLimits(work=3, wait=2),
                "Done": WipLimits(work=float("inf"), wait=2),
            },
        },
    }
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
Done = {work = inf, wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_terminal_wait_limit_is_accepted(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {"Backlog": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=float("inf"), wait=2),
            },
        },
    }
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_missing_wait_limit_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wait_limit_zero_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 0}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_extra_wip_limit_field_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3, extra = 1}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_negative_wip_limit_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = -1}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_missing_wip_limits_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_missing_state_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_extra_state_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
Elsewhere = {work = 3, wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_zero_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"In Progress" = {work = 0, wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_string_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"In Progress" = {work = "three", wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_terminal_finite_limits_are_accepted(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "Done"],
            "transitions": {"Backlog": "Done"},
            "wip_limits": {
                "Backlog": WipLimits(work=float("inf"), wait=3),
                "Done": WipLimits(work=3, wait=2),
            },
        },
    }
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = 3, wait = 2}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_empty_states_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = "invalid describe output: states must be a non-empty list\n"
    body = """states = []
transitions = {}
wip_limits = {}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_non_string_state_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = "invalid describe output: invalid state name: 1\n"
    body = """states = [1, "Done"]
transitions = {}
wip_limits = {}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_transitions_not_a_table_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = "invalid describe output: transitions must be a table\n"
    body = """states = ["Backlog", "Done"]
transitions = "Backlog to Done"
wip_limits = {}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_transition_source_not_in_states_is_rejected(
    run_describe: RunDescribe,
) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = (
        "invalid describe output: transition source not in states: 'Elsewhere'\n"
    )
    body = """states = ["Backlog", "Done"]

[transitions]
Elsewhere = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_wip_limits_not_a_table_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = "invalid describe output: wip_limits must be a table\n"
    body = """states = ["Backlog"]
transitions = {}
wip_limits = "Backlog"
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_wip_limits_entry_not_a_table_is_rejected(
    run_describe: RunDescribe,
) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = "invalid describe output: invalid wip_limits: 'Backlog' -> 3\n"
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = 3
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_bool_wip_limit_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = (
        "invalid describe output: invalid wip_limit: 'Backlog' -> work True\n"
    )
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = true, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_finite_float_wip_limit_is_rejected(run_describe: RunDescribe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    expected_output = (
        "invalid describe output: invalid wip_limit: 'Backlog' -> work 1.5\n"
    )
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = {work = 1.5, wait = 3}
Done = {work = inf, wait = inf}
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual
    assert expected_output == result.output


def test_describe_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help("""Usage: cli describe [OPTIONS]

            Describe a backend's states and transitions.

            Options:
              --help  Show this message and exit.
            """),
    }
    # WHEN
    result = runner.invoke(cli, ["describe", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual


def test_version(runner: CliRunner) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 0, "output_contains": True}
    # WHEN
    result = runner.invoke(cli, ["--version"])
    # THEN
    actual: DescribeOutcome = {
        "exit_code": result.exit_code,
        "output_contains": "0.1.0" in result.output,
    }
    assert expected == actual
