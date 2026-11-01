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
    """Write an executable mock hook script returning body."""
    hook = Path(directory) / "mock_describe.sh"
    hook.write_text("#!/usr/bin/env bash\ncat <<'EOF'\n" + body + "EOF\n")
    hook.chmod(0o755)
    return str(hook)


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
            hook = Path(tmp) / "failing.sh"
            hook.write_text("#!/usr/bin/env bash\nexit 3\n")
            hook.chmod(0o755)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = str(hook)
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
            env["DESCRIBE_HOOK"] = hook + "; touch " + str(side_effect)
            result = run_cli(env)
            self.assertFalse(side_effect.exists())
            # The injected command must not turn into a successful view.
            self.assertNotEqual(result.returncode, 0)

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


if __name__ == "__main__":
    unittest.main()
