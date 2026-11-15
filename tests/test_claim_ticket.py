"""Tests for workpull claim-ticket, through Click's runner."""

import os
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

RunClaimTicket = Callable[[str, dict[str, str], HookResult], Result]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class ClaimOutcome(TypedDict, total=False):
    exit_code: int
    output: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


class ClaimInvalidCase(NamedTuple):
    case_name: str
    hook_stdout: str


def write_mock_hook(ticket_id: str, token: str, hook_command: HookCommand) -> str:
    hook = Path("mock_claim_ticket.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'Develop':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        f'sys.stdout.write(\'ticket = "{ticket_id}"\\ntoken = "{token}"\\n\')\n'
    )
    return hook_command("mock_claim_ticket.py")


def claim_ticket_outcome(result: Result) -> ClaimOutcome:
    outcome: ClaimOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["output"] = result.output.strip()
    else:
        outcome["output"] = None
    return outcome


@pytest.fixture
def run_claim_ticket(runner: CliRunner) -> RunClaimTicket:
    def _run(state: str, env: dict[str, str], hook_result: HookResult) -> Result:
        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            if hook != env.get("CLAIM_TICKET_HOOK"):
                return HookResult(1, "", "")
            if hook_env != {"WORKPULL_STATE": state}:
                return HookResult(1, "", "")
            return hook_result

        return runner.invoke(
            cli,
            ["claim-ticket", state],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )

    return _run


@pytest.mark.parametrize("ticket_id", ["ticket-1", "0"])
def test_claim_ticket_happy_path(
    run_claim_ticket: RunClaimTicket, ticket_id: str
) -> None:
    # GIVEN
    expected: ClaimOutcome = {
        "exit_code": 0,
        "output": f'ticket = "{ticket_id}"\ntoken = "token-1"',
    }
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket(
        "Develop",
        env,
        HookResult(0, f'ticket = "{ticket_id}"\ntoken = "token-1"\n', ""),
    )
    # THEN
    assert result.exception is None
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_reversed_output_is_forwarded_verbatim(
    run_claim_ticket: RunClaimTicket,
) -> None:
    # GIVEN
    expected: ClaimOutcome = {
        "exit_code": 0,
        "output": '# claimed\ntoken = "token-1"\nticket = "ticket-1"',
    }
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket(
        "Develop",
        env,
        HookResult(
            0,
            '# claimed\ntoken = "token-1"\nticket = "ticket-1"\n',
            "",
        ),
    )
    # THEN
    assert result.exception is None
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_real_hook(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    expected: ClaimOutcome = {
        "exit_code": 0,
        "output": 'ticket = "ticket-1"\ntoken = "token-1"',
    }
    # WHEN
    with isolated_filesystem():
        hook = write_mock_hook("ticket-1", "token-1", hook_command)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hook
        result = runner.invoke(cli, ["claim-ticket", "Develop"], env=env, obj={})
    # THEN
    assert result.exception is None
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_missing_hook(run_claim_ticket: RunClaimTicket) -> None:
    # GIVEN
    expected: ClaimOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env.pop("CLAIM_TICKET_HOOK", None)
    result = run_claim_ticket(
        "Develop", env, HookResult(0, 'ticket = "ticket-1"\ntoken = "token-1"\n', "")
    )
    # THEN
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_failing_hook(run_claim_ticket: RunClaimTicket) -> None:
    # GIVEN
    expected: ClaimOutcome = {"exit_code": 3, "output": None}
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket("Develop", env, HookResult(3, "", ""))
    # THEN
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def _invalid_case_id(case: ClaimInvalidCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ClaimInvalidCase(
            case_name="empty_ticket",
            hook_stdout='ticket = ""\ntoken = "token-1"\n',
        ),
        ClaimInvalidCase(
            case_name="empty_token",
            hook_stdout='ticket = "ticket-1"\ntoken = ""\n',
        ),
        ClaimInvalidCase(
            case_name="invalid_toml",
            hook_stdout="ticket = \n",
        ),
        ClaimInvalidCase(
            case_name="missing_token",
            hook_stdout='ticket = "ticket-1"\n',
        ),
        ClaimInvalidCase(
            case_name="extra_field",
            hook_stdout='ticket = "ticket-1"\ntoken = "token-1"\nextra = 1\n',
        ),
        ClaimInvalidCase(
            case_name="non_string_ticket",
            hook_stdout='ticket = 1\ntoken = "token-1"\n',
        ),
        ClaimInvalidCase(
            case_name="non_string_token",
            hook_stdout='ticket = "ticket-1"\ntoken = 1\n',
        ),
    ],
    ids=_invalid_case_id,
)
def test_claim_ticket_invalid_output(
    run_claim_ticket: RunClaimTicket, case: ClaimInvalidCase
) -> None:
    # GIVEN
    expected: ClaimOutcome = {"exit_code": 2, "output": None}
    # WHEN
    env = dict(os.environ)
    env["CLAIM_TICKET_HOOK"] = "fake-hook"
    result = run_claim_ticket("Develop", env, HookResult(0, case.hook_stdout, ""))
    # THEN
    actual: ClaimOutcome = claim_ticket_outcome(result)
    assert expected == actual


def test_claim_ticket_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help("""Usage: cli claim-ticket [OPTIONS] STATE

            Claim a single ticket in a state.

            Options:
              --help  Show this message and exit.
            """),
    }
    # WHEN
    result = runner.invoke(cli, ["claim-ticket", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
