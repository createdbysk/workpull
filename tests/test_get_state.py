"""Tests for workpull get-state, through Click's runner."""

import os
from pathlib import Path
from typing import TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunGetState = Callable[[str, dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class StateOutcome(TypedDict, total=False):
    exit_code: int
    state: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


def write_mock_hook(state: str, hook_command: HookCommand) -> str:
    hook = Path("mock_get_state.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{state}\\n')\n"
    )
    return hook_command("mock_get_state.py")


def get_state_outcome(result: Result) -> StateOutcome:
    outcome: StateOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["state"] = result.output.strip()
    else:
        outcome["state"] = None
    return outcome


@pytest.fixture
def run_get_state(runner: CliRunner) -> RunGetState:
    def _run(ticket: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("GET_STATE_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_TICKET": ticket}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["get-state", ticket],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


def test_get_state_happy_path(run_get_state: RunGetState) -> None:
    # GIVEN
    expected: StateOutcome = {"exit_code": 0, "state": "In Progress"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-hook"
    result = run_get_state("ticket-1", env, HookResult(0, "In Progress\n", ""))
    # THEN
    assert result.exception is None
    actual: StateOutcome = get_state_outcome(result)
    assert expected == actual


def test_get_state_missing_hook(run_get_state: RunGetState) -> None:
    # GIVEN
    expected: StateOutcome = {"exit_code": 2, "state": None}
    # WHEN
    env = dict(os.environ)
    env.pop("GET_STATE_HOOK", None)
    result = run_get_state("ticket-1", env, HookResult(0, "In Progress\n", ""))
    # THEN
    actual: StateOutcome = get_state_outcome(result)
    assert expected == actual


def test_get_state_failing_hook(run_get_state: RunGetState) -> None:
    # GIVEN
    expected: StateOutcome = {"exit_code": 3, "state": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-hook"
    result = run_get_state("ticket-1", env, HookResult(3, "", ""))
    # THEN
    actual: StateOutcome = get_state_outcome(result)
    assert expected == actual


def test_get_state_empty_state(run_get_state: RunGetState) -> None:
    # GIVEN
    expected: StateOutcome = {"exit_code": 2, "state": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-hook"
    result = run_get_state("ticket-1", env, HookResult(0, "", ""))
    # THEN
    actual: StateOutcome = get_state_outcome(result)
    assert expected == actual


def test_get_state_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: StateOutcome = {"exit_code": 0, "state": "In Progress"}
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("In Progress", hook_command)
        env = dict(os.environ)
        env["GET_STATE_HOOK"] = hook
        result = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: StateOutcome = get_state_outcome(result)
    assert expected == actual


def test_get_state_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli get-state [OPTIONS] TICKET

            Get a ticket's current state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["get-state", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
