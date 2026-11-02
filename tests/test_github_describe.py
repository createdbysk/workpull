"""Tests for the GitHub issues describe mock, which validates
the shape of the describe contract.

Tests drive the CLI as a subprocess with DESCRIBE_HOOK pointing
at the adapter script, with an explicit environment. Describe
needs no network and no token, so no live GitHub call is made
here.
"""

import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "plugins" / "github" / "describe.py"


class View(TypedDict):
    states: list[str]
    claim: dict[str, str]


class Outcome(TypedDict, total=False):
    exit_code: int
    view: View | None
    output_contains: bool


def parse_view(text: str) -> View:
    """Parse TOML output as a View. Values are Any from TOML."""
    parsed = tomllib.loads(text)
    return View(states=parsed["states"], claim=parsed["claim"])


def run_cli(env: dict[str, str]):
    """Run `python -m workpull describe` with an explicit env."""
    return subprocess.run(
        [sys.executable, "-m", "workpull", "describe"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestGitHubDescribe(unittest.TestCase):
    def test_cli_via_github_adapter(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {"states": ["Open", "Closed"], "claim": {"Open": "Closed"}},
        }
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = f"{Path(sys.executable).as_posix()} {ADAPTER.as_posix()}"
        # WHEN
        result = run_cli(env)
        # THEN
        actual: Outcome = {
            "exit_code": result.returncode,
            "view": parse_view(result.stdout) if result.returncode == 0 else None,
        }
        self.assertEqual(expected, actual)

    def test_adapter_direct_output_is_exact(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {"states": ["Open", "Closed"], "claim": {"Open": "Closed"}},
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
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
