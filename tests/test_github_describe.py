"""Tests for the GitHub issues describe mock, which validates
the shape of the describe contract.

Tests drive the CLI through Click's test runner with
DESCRIBE_HOOK pointing at the adapter script, with an explicit
environment. The hook itself still runs as a real subprocess,
through the real run_hook. Describe needs no network and no
token, so no live GitHub call is made here.
"""

import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, TypedDict

import pytest
from click.testing import CliRunner, Result

from workpull.cli import cli

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "plugins" / "github" / "describe.py"


RunCli = Callable[[dict[str, str]], Result]
HookCommand = Callable[[str], str]


# A WIP limit is a positive int, or inf, the only float allowed.
class WipLimits(NamedTuple):
    work: int | float
    wait: int | float


class View(TypedDict):
    states: list[str]
    transitions: dict[str, str]
    wip_limits: dict[str, WipLimits]


class Outcome(TypedDict, total=False):
    exit_code: int
    view: View | None
    output_contains: bool


def parse_view(text: str) -> View:
    """Parse TOML output as a View. Values are Any from TOML."""
    parsed = tomllib.loads(text)
    return View(
        states=parsed["states"],
        transitions=parsed["transitions"],
        wip_limits={
            state: WipLimits(work=limits["work"], wait=limits["wait"])
            for state, limits in parsed["wip_limits"].items()
        },
    )


@pytest.fixture
def run_cli(runner: CliRunner) -> RunCli:
    def _run(env: dict[str, str]) -> Result:
        """Run the CLI's describe command with an explicit env."""
        return runner.invoke(cli, ["describe"], env=env, obj={})

    return _run


def test_cli_via_github_adapter(run_cli: RunCli, hook_command: HookCommand) -> None:
    # GIVEN
    expected: Outcome = {
        "exit_code": 0,
        "view": {
            "states": ["Open", "Closed"],
            "transitions": {"Open": "Closed"},
            "wip_limits": {
                "Open": WipLimits(work=float("inf"), wait=3),
                "Closed": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
    }
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = hook_command(ADAPTER.as_posix())
    # WHEN
    result = run_cli(env)
    # THEN
    actual: Outcome = {
        "exit_code": result.exit_code,
        "view": parse_view(result.output) if result.exit_code == 0 else None,
    }
    assert expected == actual


def test_adapter_direct_output_is_exact() -> None:
    # GIVEN
    expected: Outcome = {
        "exit_code": 0,
        "view": {
            "states": ["Open", "Closed"],
            "transitions": {"Open": "Closed"},
            "wip_limits": {
                "Open": WipLimits(work=float("inf"), wait=3),
                "Closed": WipLimits(work=float("inf"), wait=float("inf")),
            },
        },
        "output_contains": False,
    }
    # WHEN
    result = subprocess.run(
        [sys.executable, str(ADAPTER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # THEN
    actual: Outcome = {
        "exit_code": result.returncode,
        "view": parse_view(result.stdout) if result.returncode == 0 else None,
        "output_contains": "Backlog" in result.stdout,
    }
    assert expected == actual
