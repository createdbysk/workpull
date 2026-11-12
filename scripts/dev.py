"""Workpull developer tasks, stdlib only, cross-platform.

Run with the system Python, no venv needed to run this
script itself:

    python scripts/dev.py setup
    python scripts/dev.py test
    python scripts/dev.py lint
    python scripts/dev.py type

Installation requires a venv. There is no supported system install.
"""

import argparse
from typing import Any
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT_FILES = [
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
    ".agents/skills/workpull/SKILL.md",
    ".agents/skills/develop-workpull/SKILL.md",
    "requirements/",
    "design/",
    "implementation/",
]
PYTHON_FILES = ["workpull", "tests", "scripts", "adapters", "plugins"]


def venv_python() -> Path:
    """Path to the venv Python, Windows or POSIX layout."""
    if sys.platform == "win32":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def run(command: list[str], **kwargs: Any) -> int:
    return subprocess.run(command, cwd=ROOT, **kwargs).returncode


def cmd_setup(_args: argparse.Namespace) -> int:
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


def in_venv() -> bool:
    """True when running inside an activated venv."""
    import os

    return sys.prefix != sys.base_prefix or bool(os.environ.get("VIRTUAL_ENV"))


def cmd_install(_args: argparse.Namespace) -> int:
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


def cmd_test(_args: argparse.Namespace) -> int:
    python = venv_python() if venv_python().exists() else sys.executable
    return run([str(python), "-m", "pytest", "tests", "-q"])


def cmd_type(_args: argparse.Namespace) -> int:
    pyrefly = shutil.which("pyrefly")
    if not pyrefly:
        for name in ("pyrefly", "pyrefly.exe"):
            venv_pyrefly = venv_python().parent / name
            if venv_pyrefly.exists():
                pyrefly = str(venv_pyrefly)
                break
    if not pyrefly:
        print(
            "error: pyrefly not found. Run: python scripts/dev.py setup",
            file=sys.stderr,
        )
        return 1
    return run([pyrefly, "check", *PYTHON_FILES])


def cmd_lint(_args: argparse.Namespace) -> int:
    pymarkdown = shutil.which("pymarkdown")
    if not pymarkdown:
        for name in ("pymarkdown", "pymarkdown.exe"):
            venv_pymarkdown = venv_python().parent / name
            if venv_pymarkdown.exists():
                pymarkdown = str(venv_pymarkdown)
                break
    if not pymarkdown:
        print(
            "error: pymarkdown not found. Run: python scripts/dev.py setup",
            file=sys.stderr,
        )
        return 1
    ruff = shutil.which("ruff")
    if not ruff:
        for name in ("ruff", "ruff.exe"):
            venv_ruff = venv_python().parent / name
            if venv_ruff.exists():
                ruff = str(venv_ruff)
                break
    if not ruff:
        print(
            "error: ruff not found. Run: python scripts/dev.py setup",
            file=sys.stderr,
        )
        return 1
    markdown_code = run(
        [pymarkdown, "--config", ".pymarkdown.json", "scan", *LINT_FILES]
    )
    ruff_code = run([ruff, "check", "--output-format", "concise", *PYTHON_FILES])
    return 1 if markdown_code or ruff_code else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Workpull developer tasks.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Create .venv and install dev deps.")
    sub.add_parser("install", help="Install, only inside an activated venv.")
    sub.add_parser("test", help="Run pytest.")
    sub.add_parser("lint", help="Run pymarkdown on docs and Ruff on Python.")
    sub.add_parser("type", help="Run pyrefly type check.")
    args = parser.parse_args(argv)
    commands = {
        "setup": cmd_setup,
        "install": cmd_install,
        "test": cmd_test,
        "lint": cmd_lint,
        "type": cmd_type,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
