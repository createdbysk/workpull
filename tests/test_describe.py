"""Tests for workpull describe, through Click's runner."""

import os
import tomllib
from pathlib import Path
from typing import TypedDict

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = inf
"""


class View(TypedDict):
    states: list[str]
    transitions: dict[str, str]
    wip_limits: dict[str, int | float]


class DescribeOutcome(TypedDict, total=False):
    exit_code: int
    view: View | None
    output_contains: bool


class SideEffectOutcome(TypedDict, total=False):
    side_effect_exists: bool


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(body: str, hook_command: Callable[[str], str]) -> str:
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
        wip_limits=parsed["wip_limits"],
    )


def describe_outcome(result: Result) -> DescribeOutcome:
    outcome: DescribeOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["view"] = parse_view(result.output)
    else:
        outcome["view"] = None
    return outcome


@pytest.fixture
def run_describe(runner: CliRunner):
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


def test_happy_path(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {"states": ["Backlog", "Done"], "transitions": {"Backlog": "Done"}, "wip_limits": {"Backlog": float("inf")}},
    }
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, TRIVIAL_VIEW, ""))
    # THEN
    assert result.exception is None
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_describe_real_hook(runner, isolated_filesystem, hook_command) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {"states": ["Backlog", "Done"], "transitions": {"Backlog": "Done"}, "wip_limits": {"Backlog": float("inf")}},
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


def test_missing_hook(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    # WHEN
    env = dict(os.environ)
    env.pop("DESCRIBE_HOOK", None)
    result = run_describe(env, HookResult(0, TRIVIAL_VIEW, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_failing_hook(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 3, "view": None}
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(3, "", ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_invalid_toml(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, "this is not toml [\n", ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_transition_to_unknown_state(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Elsewhere"

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_hook_command_injection_is_not_executed(runner, isolated_filesystem, hook_command) -> None:
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


def test_hook_command_injection_unspaced_is_not_executed(runner, isolated_filesystem, hook_command) -> None:
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


def test_duplicate_states_are_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_self_loop_transition_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Backlog"

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_backwards_transition_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Done = "Backlog"

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_whitespace_padded_state_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog ", "Done"]

[transitions]
"Backlog " = "Done"

[wip_limits]
"Backlog " = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_empty_transitions_means_all_terminal(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {"states": ["Backlog", "Done"], "transitions": {}, "wip_limits": {}},
    }
    body = """states = ["Backlog", "Done"]

[transitions]

[wip_limits]
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_hook_comment_is_not_printed(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {"states": ["Backlog", "Done"], "transitions": {"Backlog": "Done"}, "wip_limits": {"Backlog": float("inf")}},
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


def test_state_name_with_shell_metacharacters_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog; rm -rf /", "Done"]

[transitions]
"Backlog; rm -rf /" = "Done"

[wip_limits]
"Backlog; rm -rf /" = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_spaced_state_produces_valid_toml(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["In Progress", "Done"],
            "transitions": {"In Progress": "Done"},
            "wip_limits": {"In Progress": 3},
        },
    }
    body = """states = ["In Progress", "Done"]

[transitions]
"In Progress" = "Done"

[wip_limits]
"In Progress" = 3
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_unhashable_state_is_rejected(run_describe) -> None:
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


def test_unhashable_transition_target_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = ["Done"]

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_finite_wip_limit_is_accepted(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {
        "exit_code": 0,
        "view": {
            "states": ["Backlog", "In Progress", "Done"],
            "transitions": {"Backlog": "In Progress", "In Progress": "Done"},
            "wip_limits": {"Backlog": float("inf"), "In Progress": 3},
        },
    }
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = inf
"In Progress" = 3
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_missing_wip_limits_is_rejected(run_describe) -> None:
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


def test_wip_limit_missing_state_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = inf
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_extra_state_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = inf
Elsewhere = 3
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_zero_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = inf
"In Progress" = 0
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_wip_limit_string_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "In Progress", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = inf
"In Progress" = "three"
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_terminal_state_in_wip_limits_is_rejected(run_describe) -> None:
    # GIVEN
    expected: DescribeOutcome = {"exit_code": 2, "view": None}
    body = """states = ["Backlog", "Done"]

[transitions]
Backlog = "Done"

[wip_limits]
Backlog = inf
Done = 3
"""
    # WHEN
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-hook"
    result = run_describe(env, HookResult(0, body, ""))
    # THEN
    actual: DescribeOutcome = describe_outcome(result)
    assert expected == actual


def test_describe_help(runner, normalize_help) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli describe [OPTIONS]

            Describe a backend's states and transitions.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["describe", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual


def test_version(runner) -> None:
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
