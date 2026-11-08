"""Shared test helpers for workpull tests."""

import contextlib
import os
import sys
import tempfile
from pathlib import Path


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
