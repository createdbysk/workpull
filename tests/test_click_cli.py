"""Tests for the Click CLI, in an isolated filesystem.

Tests drive the CLI through Click's runner, not a subprocess,
except the module-entry test, which proves `python -m workpull`
still works.
"""

import contextlib
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from click.testing import CliRunner

from workpull.cli import cli

ROOT = Path(__file__).resolve().parents[1]

TRIVIAL_VIEW = """states = ["Backlog", "Done"]

[claim]
Backlog = "Done"
"""


@contextlib.contextmanager
def isolated_filesystem():
    """Temporary directory as working directory, cleaned up after.

    Click deprecated its own isolated_filesystem helper, so this
    test uses tempfile directly, with the same effect.
    """
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


class ClickCliTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_describe_in_isolated_filesystem(self):
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.runner.invoke(cli, ["describe"], env=env)
            self.assertEqual(result.exit_code, 0, result.output)
            view = tomllib.loads(result.output)
            self.assertEqual(view["states"], ["Backlog", "Done"])
            self.assertEqual(view["claim"], {"Backlog": "Done"})

    def test_describe_writes_no_files_outside_isolated_filesystem(self):
        with isolated_filesystem():
            hook = write_mock_hook(TRIVIAL_VIEW)
            env = dict(os.environ)
            env["DESCRIBE_HOOK"] = hook
            result = self.runner.invoke(cli, ["describe"], env=env)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(
                sorted(p.name for p in Path(".").iterdir()),
                ["mock_describe.py"],
            )

    def test_missing_hook_fails(self):
        with isolated_filesystem():
            env = dict(os.environ)
            env.pop("DESCRIBE_HOOK", None)
            result = self.runner.invoke(cli, ["describe"], env=env)
            self.assertNotEqual(result.exit_code, 0)
            self.assertNotIn("Backlog", result.output)

    def test_help_lists_describe(self):
        result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("describe", result.output)

    def test_version(self):
        result = self.runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("0.1.0", result.output)

    def test_unknown_command_fails(self):
        result = self.runner.invoke(cli, ["claim"])
        self.assertNotEqual(result.exit_code, 0)

    def test_module_entry_still_works(self):
        result = subprocess.run(
            [sys.executable, "-m", "workpull", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("describe", result.stdout)


if __name__ == "__main__":
    unittest.main()
