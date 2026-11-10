"""Tests for workpull count, through Click's runner."""

import os
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunCount = Callable[[str, dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class CountOutcome(TypedDict, total=False):
    exit_code: int
    output: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(state: str, hook_command: HookCommand) -> str:
    hook = Path("mock_count.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'In Progress':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('wait = 2\\nwork = 3\\n')\n"
    )
    return hook_command("mock_count.py")


class CountInvalidCase(NamedTuple):
    case_name: str
    hook_stdout: str


def count_outcome(result: Result) -> CountOutcome:
    outcome: CountOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["output"] = result.output.strip()
    else:
        outcome["output"] = None
    return outcome


@pytest.fixture
def run_count(runner: CliRunner) -> RunCount:
    def _run(state: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("COUNT_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_STATE": state}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["count", state],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


def test_count_happy_path(run_count: RunCount) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 0, "output": "wait = 2\nwork = 3"}
    # WHEN
    env = dict(os.environ)
    env["COUNT_HOOK"] = "fake-hook"
    result = run_count("In Progress", env, HookResult(0, "wait = 2\nwork = 3\n", ""))
    # THEN
    assert result.exception is None
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def test_count_missing_hook(run_count: RunCount) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env.pop("COUNT_HOOK", None)
    result = run_count("In Progress", env, HookResult(0, "wait = 2\nwork = 3\n", ""))
    # THEN
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def test_count_failing_hook(run_count: RunCount) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 3, "output": None}
    # WHEN
    env = dict(os.environ)
    env["COUNT_HOOK"] = "fake-hook"
    result = run_count("In Progress", env, HookResult(3, "", ""))
    # THEN
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def test_count_invalid_toml(run_count: RunCount) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["COUNT_HOOK"] = "fake-hook"
    result = run_count("In Progress", env, HookResult(0, "wait = \n", ""))
    # THEN
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def _invalid_case_id(case: CountInvalidCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        CountInvalidCase(
            case_name="missing_work",
            hook_stdout="wait = 2\n",
        ),
        CountInvalidCase(
            case_name="missing_wait",
            hook_stdout="work = 3\n",
        ),
        CountInvalidCase(
            case_name="extra_field",
            hook_stdout="wait = 2\nwork = 3\nextra = 1\n",
        ),
        CountInvalidCase(
            case_name="wait_string",
            hook_stdout='wait = "2"\nwork = 3\n',
        ),
        CountInvalidCase(
            case_name="wait_negative",
            hook_stdout="wait = -1\nwork = 3\n",
        ),
        CountInvalidCase(
            case_name="wait_bool",
            hook_stdout="wait = true\nwork = 3\n",
        ),
    ],
    ids=_invalid_case_id,
)
def test_count_invalid_output(
    run_count: RunCount, case: CountInvalidCase
) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["COUNT_HOOK"] = "fake-hook"
    result = run_count("In Progress", env, HookResult(0, case.hook_stdout, ""))
    # THEN
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def test_count_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: CountOutcome = {"exit_code": 0, "output": "wait = 2\nwork = 3"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("In Progress", hook_command)
        env = dict(os.environ)
        env["COUNT_HOOK"] = hook
        result = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: CountOutcome = count_outcome(result)
    assert expected == actual


def test_count_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli count [OPTIONS] STATE

            Count tickets in a state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["count", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
