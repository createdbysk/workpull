"""Workpull developer tasks, stdlib only, cross-platform.

Run with the system Python, no venv needed to run this
script itself:

    python scripts/dev.py setup
    python scripts/dev.py test
    python scripts/dev.py lint

Installation requires a venv. There is no supported system install.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT_FILES = [
    "AGENTS.md",
    "README.md",
    ".agents/skills/workpull/SKILL.md",
    ".agents/skills/develop-workpull/SKILL.md",
    "requirements/",
    "design/",
    "implementation/",
]


def venv_python():
    """Path to the venv Python, Windows or POSIX layout."""
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, **kwargs).returncode


def cmd_setup(_args):
    """Create .venv if missing, install workpull with dev deps."""
    import venv

    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        venv.create(venv_dir, with_pip=True)
    python = venv_python()
    code = run([str(python), "-m", "pip", "install", "-q", "--upgrade", "pip"])
    if code:
        return code
    code = run([str(python), "-m", "pip", "install", "-q", "-e", ".[dev]"])
    if code:
        return code
    if sys.platform == "win32":
        print("Venv ready. Activate it with: .venv\\Scripts\\activate")
    else:
        print("Venv ready. Activate it with: source .venv/bin/activate")
    return 0


def in_venv():
    """True when running inside an activated venv."""
    import os

    return sys.prefix != sys.base_prefix or bool(os.environ.get("VIRTUAL_ENV"))


def cmd_install(_args):
    """Install only inside an activated venv. Refuses system installs."""
    if not in_venv():
        print(
            "error: activate a venv first: source .venv/bin/activate "
            "(or .venv\\Scripts\\activate on Windows)",
            file=sys.stderr,
        )
        print("or run: python scripts/dev.py setup", file=sys.stderr)
        return 1
    return run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"])


def cmd_test(_args):
    python = venv_python() if venv_python().exists() else sys.executable
    return run([str(python), "-m", "unittest", "discover", "-s", "tests"])


def cmd_lint(_args):
    pymarkdown = shutil.which("pymarkdown")
    if not pymarkdown:
        venv_pymarkdown = venv_python().parent / "pymarkdown"
        if venv_pymarkdown.exists():
            pymarkdown = str(venv_pymarkdown)
    if not pymarkdown:
        print(
            "error: pymarkdown not found. Run: python scripts/dev.py setup",
            file=sys.stderr,
        )
        return 1
    return run([pymarkdown, "--config", ".pymarkdown.json", "scan", *LINT_FILES])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Workpull developer tasks.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Create .venv and install dev deps.")
    sub.add_parser("install", help="Install, only inside an activated venv.")
    sub.add_parser("test", help="Run unittest.")
    sub.add_parser("lint", help="Run pymarkdown on docs.")
    args = parser.parse_args(argv)
    commands = {
        "setup": cmd_setup,
        "install": cmd_install,
        "test": cmd_test,
        "lint": cmd_lint,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
