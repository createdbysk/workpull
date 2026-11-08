"""Shared pytest fixtures for workpull tests."""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
