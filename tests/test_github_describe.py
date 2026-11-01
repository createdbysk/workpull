"""Tests for the GitHub issues describe adapter.

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

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "plugins" / "github" / "describe.py"


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


class TestGitHubDescribe(unittest.TestCase):
    def test_cli_via_github_adapter(self):
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = f"{sys.executable} {ADAPTER}"
        result = run_cli(env)
        self.assertEqual(result.returncode, 0, result.stderr)
        view = tomllib.loads(result.stdout)
        self.assertEqual(view["states"], ["Open", "Closed"])
        self.assertEqual(view["claim"], {"Open": "Closed"})

    def test_adapter_direct_output_is_exact(self):
        result = subprocess.run(
            [sys.executable, str(ADAPTER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        view = tomllib.loads(result.stdout)
        self.assertEqual(set(view), {"states", "claim"})
        self.assertEqual(view["states"], ["Open", "Closed"])
        self.assertEqual(view["claim"], {"Open": "Closed"})
        self.assertNotIn("Backlog", result.stdout)


if __name__ == "__main__":
    unittest.main()
