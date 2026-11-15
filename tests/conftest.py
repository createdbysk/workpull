"""Shared pytest fixtures for workpull tests."""

import contextlib
import os
import sys
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def normalize_help() -> Callable[[str], str]:
    def _normalize_help(text: str) -> str:
        """Collapse consecutive whitespace to a single space.

        The expected string in a help test stays human-readable,
        formatted like Click output. This turns it, and the
        actual Click output, into the same compressed form,
        so minor format changes do not become test failures.
        """
        return " ".join(text.split())

    return _normalize_help


@pytest.fixture
def isolated_filesystem() -> Callable[[], contextlib.AbstractContextManager[str]]:
    @contextlib.contextmanager
    def _isolated_filesystem() -> Generator[str, None, None]:
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                yield tmp
            finally:
                os.chdir(old)

    return _isolated_filesystem


@pytest.fixture
def hook_command() -> Callable[[str], str]:
    def _hook_command(script: str) -> str:
        return f"{Path(sys.executable).as_posix()} {script}"

    return _hook_command
