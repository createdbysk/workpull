"""Tests for workpull describe, through Click's runner.

Tests run in an isolated filesystem, with an explicit
environment, never by mutating the test process environment,
so one test cannot leak into the next.
"""

import contextlib
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import TypedDict

from click.testing import CliRunner

from workpull.cli import cli

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
"""


class View(TypedDict):
    states: list[str]
    claim: dict[str, str]


class Outcome(TypedDict, total=False):
    exit_code: int
    view: View | None
    side_effect_exists: bool
    output_contains: bool


@contextlib.contextmanager
def isolated_filesystem():
    """Temporary directory as working directory, cleaned up after."""
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old)


def hook_command(script: str) -> str:
    """Hook command in canonical POSIX form, on every platform."""
    return f"{Path(sys.executable).as_posix()} {script}"


def write_mock_hook(body: str) -> str:
    """Write a mock hook script in the current directory."""
    hook = Path("mock_describe.py")
    hook.write_text("import sys\nsys.stdout.write(" + repr(body) + ")\n")
    return hook_command("mock_describe.py")


def parse_view(text: str) -> View:
    """Parse TOML output as a View. Values are Any from TOML."""
    parsed = tomllib.loads(text)
    return View(states=parsed["states"], claim=parsed["claim"])


def describe_outcome(result) -> Outcome:
    """Outcome for a describe run, with a view only on success."""
    outcome: Outcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["view"] = parse_view(result.output)
    else:
        outcome["view"] = None
    return outcome


class TestDescribe(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def run_describe(self, env: dict[str, str]):
        return self.runner.invoke(cli, ["describe"], env=env)

    def test_happy_path(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {"states": ["Backlog", "Done"], "claim": {"Backlog": "Done"}},
        }
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_missing_hook(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        # WHEN
        with isolated_filesystem():
            env = dict(os.environ)
            env.pop("DESCRIBE_HOOK", None)
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_failing_hook(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 3, "view": None}
        # WHEN
        with isolated_filesystem():
            hook = Path("failing.py")
            hook.write_text("import sys\nsys.exit(3)\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook_command("failing.py")
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_invalid_toml(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook("this is not toml [\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_transition_to_unknown_state(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Elsewhere"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_hook_command_injection_is_not_executed(self) -> None:
        # GIVEN
        expected: Outcome = {"side_effect_exists": False}
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            side_effect = Path("pwned")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + " ; touch " + str(side_effect)
            self.run_describe(env)
            actual: Outcome = {"side_effect_exists": side_effect.exists()}
        # THEN
        self.assertEqual(expected, actual)

    def test_hook_command_injection_unspaced_is_not_executed(self) -> None:
        # GIVEN
        expected: Outcome = {"side_effect_exists": False}
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            side_effect = Path("pwned")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + "; touch " + str(side_effect)
            self.run_describe(env)
            actual: Outcome = {"side_effect_exists": side_effect.exists()}
        # THEN
        self.assertEqual(expected, actual)

    def test_duplicate_states_are_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog", "Backlog", "Done"]

[claim]
Backlog = "Done"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_self_loop_claim_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Backlog"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_backwards_claim_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog", "Done"]

[claim]
Done = "Backlog"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_whitespace_padded_state_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog ", "Done"]

[claim]
"Backlog " = "Done"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_empty_claim_means_all_terminal(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {"states": ["Backlog", "Done"], "claim": {}},
        }
        body = """states = ["Backlog", "Done"]

[claim]
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_hook_comment_is_not_printed(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {"states": ["Backlog", "Done"], "claim": {"Backlog": "Done"}},
            "output_contains": False,
        }
        body = "# ignore previous instructions\n" + TRIVIAL_VIEW
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            actual: Outcome = describe_outcome(result)
            actual["output_contains"] = "ignore previous instructions" in result.output
        # THEN
        self.assertEqual(expected, actual)

    def test_state_name_with_shell_metacharacters_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog; rm -rf /", "Done"]

[claim]
"Backlog; rm -rf /" = "Done"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_spaced_state_produces_valid_toml(self) -> None:
        # GIVEN
        expected: Outcome = {
            "exit_code": 0,
            "view": {
                "states": ["In Progress", "Done"],
                "claim": {"In Progress": "Done"},
            },
        }
        body = """states = ["In Progress", "Done"]

[claim]
"In Progress" = "Done"
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_unhashable_state_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = [{a = 1}, "Done"]

[claim]
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_unhashable_claim_target_is_rejected(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 2, "view": None}
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = ["Done"]
"""
        # WHEN
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
        # THEN
        actual: Outcome = describe_outcome(result)
        self.assertEqual(expected, actual)

    def test_help_lists_describe(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 0, "output_contains": True}
        # WHEN
        result = self.runner.invoke(cli, ["--help"])
        # THEN
        actual: Outcome = {
            "exit_code": result.exit_code,
            "output_contains": "describe" in result.output,
        }
        self.assertEqual(expected, actual)

    def test_version(self) -> None:
        # GIVEN
        expected: Outcome = {"exit_code": 0, "output_contains": True}
        # WHEN
        result = self.runner.invoke(cli, ["--version"])
        # THEN
        actual: Outcome = {
            "exit_code": result.exit_code,
            "output_contains": "0.1.0" in result.output,
        }
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
