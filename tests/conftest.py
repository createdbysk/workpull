"""Shared pytest fixtures for workpull tests."""

from collections.abc import Callable

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
