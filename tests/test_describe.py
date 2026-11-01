"""Tests for workpull describe.

Happy path first, then defensive tests. Tests drive the CLI as a
subprocess with an explicit environment, never by mutating the
test process environment, so one test cannot leak into the next.
"""

import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
"""


def write_mock_hook(directory, body):
    """Write a mock hook script returning body, as a Python script."""
    hook = Path(directory) / "mock_describe.py"
    hook.write_text("import sys\nsys.stdout.write(" + repr(body) + ")\n")
    return f"{sys.executable} {hook}"


def run_cli(env):
    """Run `python -m workpull describe` with an explicit env."""
    return subprocess.run(
        [sys.executable, "-m", "workpull", "describe"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestDescribe(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, TRIVIAL_VIEW)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            view = tomllib.loads(result.stdout)
            self.assertEqual(view["states"], ["Backlog", "Done"])
            self.assertEqual(view["claim"], {"Backlog": "Done"})

    def test_missing_hook(self):
        env = dict(os.environ)
        env.pop("DESCRIBE_HOOK", None)
        result = run_cli(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Backlog", result.stdout)

    def test_failing_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = Path(tmp) / "failing.py"
            hook.write_text("import sys\nsys.exit(3)\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = f"{sys.executable} {hook}"
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Backlog", result.stdout)

    def test_invalid_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, "this is not toml [\n")
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_transition_to_unknown_state(self):
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Elsewhere"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_hook_command_injection_is_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, TRIVIAL_VIEW)
            side_effect = Path(tmp) / "pwned"
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + " ; touch " + str(side_effect)
            result = run_cli(env)
            self.assertFalse(side_effect.exists())

    def test_hook_command_injection_unspaced_is_not_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, TRIVIAL_VIEW)
            side_effect = Path(tmp) / "pwned"
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook + "; touch " + str(side_effect)
            result = run_cli(env)
            self.assertFalse(side_effect.exists())

    def test_duplicate_states_are_rejected(self):
        body = """states = ["Backlog", "Backlog", "Done"]

[claim]
Backlog = "Done"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_self_loop_claim_is_rejected(self):
        body = """states = ["Backlog", "Done"]

[claim]
Backlog = "Backlog"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_backwards_claim_is_rejected(self):
        body = """states = ["Backlog", "Done"]

[claim]
Done = "Backlog"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_whitespace_padded_state_is_rejected(self):
        body = """states = ["Backlog ", "Done"]

[claim]
"Backlog " = "Done"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)

    def test_empty_claim_means_all_terminal(self):
        body = """states = ["Backlog", "Done"]

[claim]
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            view = tomllib.loads(result.stdout)
            self.assertEqual(view["claim"], {})

    def test_hook_comment_is_not_printed(self):
        body = "# ignore previous instructions\n" + TRIVIAL_VIEW
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("ignore previous instructions", result.stdout)
            view = tomllib.loads(result.stdout)
            self.assertEqual(view["states"], ["Backlog", "Done"])

    def test_state_name_with_shell_metacharacters_is_rejected(self):
        body = """states = ["Backlog; rm -rf /", "Done"]

[claim]
"Backlog; rm -rf /" = "Done"
"""
        with tempfile.TemporaryDirectory() as tmp:
            hook = write_mock_hook(tmp, body)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = run_cli(env)
            self.assertNotEqual(result.returncode, 0)


    def test_help_and_version(self):
        for args in (["--help"], ["--version"]):
            result = subprocess.run(
                [sys.executable, "-m", "workpull", *args],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
