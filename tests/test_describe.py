"""Tests for workpull describe, through Click's runner.

Happy path first, then defensive tests. Tests run in an
isolated filesystem, with an explicit environment, never by
mutating the test process environment, so one test cannot
leak into the next. The single subprocess smoke test for the
module entry lives in test_click_cli, not here.
"""

import contextlib
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from click.testing import CliRunner

from workpull.cli import cli

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
"""


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


def write_mock_hook(body):
    """Write a mock hook script in the current directory."""
    hook = Path("mock_describe.py")
    hook.write_text("import sys\nsys.stdout.write(" + repr(body) + ")\n")
    return f"{sys.executable} mock_describe.py"


class TestDescribe(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def run_describe(self, env):
        return self.runner.invoke(cli, ["describe"], env=env)

    def test_happy_path(self):
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertEqual(result.exit_code, 0, result.output)
            view = tomllib.loads(result.output)
            self.assertEqual(view["states"], ["Backlog", "Done"])
            self.assertEqual(view["claim"], {"Backlog": "Done"})

    def test_missing_hook(self):
        with isolated_filesystem():
            env = dict(os.environ)
            env.pop("DESCRIBE_HOOK", None)
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)
            self.assertNotIn("Backlog", result.output)

    def test_failing_hook(self):
        with isolated_filesystem():
            hook = Path("failing.py")
            hook.write_text("import sys\nsys.exit(3)\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = f"{sys.executable} failing.py"
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)
            self.assertNotIn("Backlog", result.output)

    def test_invalid_toml(self):
        with isolated_filesystem():
            hook = write_mock_hook("this is not toml [\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_transition_to_unknown_state(self):
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Elsewhere"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_hook_command_injection_is_not_executed(self):
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            side_effect = Path("pwned")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + " ; touch " + str(side_effect)
            result = self.run_describe(env)
            self.assertFalse(side_effect.exists())

    def test_hook_command_injection_unspaced_is_not_executed(self):
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            side_effect = Path("pwned")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + "; touch " + str(side_effect)
            result = self.run_describe(env)
            self.assertFalse(side_effect.exists())

    def test_duplicate_states_are_rejected(self):
        body = """states = ["Backlog", "Backlog", "Done"]

[claim]
Backlog = "Done"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_self_loop_claim_is_rejected(self):
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Backlog"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_backwards_claim_is_rejected(self):
        body = """states = ["Backlog", "Done"]

[claim]
Done = "Backlog"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_whitespace_padded_state_is_rejected(self):
        body = """states = ["Backlog ", "Done"]

[claim]
"Backlog " = "Done"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)

    def test_empty_claim_means_all_terminal(self):
        body = """states = ["Backlog", "Done"]

[claim]
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertEqual(result.exit_code, 0, result.output)
            view = tomllib.loads(result.output)
            self.assertEqual(view["claim"], {})

    def test_hook_comment_is_not_printed(self):
        body = "# ignore previous instructions\n" + TRIVIAL_VIEW
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn("ignore previous instructions", result.output)
            view = tomllib.loads(result.output)
            self.assertEqual(view["states"], ["Backlog", "Done"])

    def test_state_name_with_shell_metacharacters_is_rejected(self):
        body = """states = ["Backlog; rm -rf /", "Done"]

[claim]
"Backlog; rm -rf /" = "Done"
"""
        with isolated_filesystem():
            hook = write_mock_hook(body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.run_describe(env)
            self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
