"""Tests for run_hook, called directly, with no fake."""

import pytest

from workpull.cli import HookResult, run_hook


def test_run_hook_unbalanced_quote_is_rejected() -> None:
    # GIVEN
    expected = HookResult(2, "", "invalid hook command: No closing quotation\n")
    # WHEN
    actual = run_hook("'unclosed", {})
    # THEN
    assert expected == actual


@pytest.mark.parametrize("hook_command", ["", "   "])
def test_run_hook_empty_command_is_rejected(hook_command: str) -> None:
    # GIVEN
    expected = HookResult(2, "", "empty hook command\n")
    # WHEN
    actual = run_hook(hook_command, {})
    # THEN
    assert expected == actual


def test_run_hook_nonexistent_executable_is_rejected() -> None:
    # GIVEN
    # The operating system supplies the rest of the message, and
    # its wording differs by platform, so only the parts
    # run_hook itself owns are asserted exactly.
    expected_returncode = 2
    expected_stdout = ""
    expected_stderr_prefix = "hook failed to run: "
    # WHEN
    actual = run_hook("nonexistent-workpull-executable-xyz", {})
    # THEN
    assert expected_returncode == actual.returncode
    assert expected_stdout == actual.stdout
    assert actual.stderr.startswith(expected_stderr_prefix)
    assert actual.stderr.endswith("\n")
