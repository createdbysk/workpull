"""Tests for workpull transition, through Click's runner."""

import os
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli


class TransitionRun(NamedTuple):
    result: Result
    called_hooks: tuple[str, ...]


RunTransition = Callable[
    [str, str, str, dict[str, str], HookResult, HookResult, HookResult, HookResult, HookResult],
    TransitionRun,
]
IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class TicketOutcome(TypedDict, total=False):
    exit_code: int
    ticket_id: str | None


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


class TransitionCheckCase(NamedTuple):
    case_name: str
    to_state: str
    wait_count: int


class TransitionMissingHookCase(NamedTuple):
    case_name: str
    missing_hook: str


class TransitionFailingHookCase(NamedTuple):
    case_name: str
    failing_hook: str


class TransitionInvalidTomlCase(NamedTuple):
    case_name: str
    invalid_hook: str


class TransitionHappyCase(NamedTuple):
    case_name: str
    current_state: str
    to_state: str
    wait_count: int
    ticket_id: str


class TransitionUnknownStateCase(NamedTuple):
    case_name: str
    to_state: str
    current_state: str
    count_called: bool


class TransitionHookFailureCase(NamedTuple):
    case_name: str
    transition_hook_set: bool
    transition_result: HookResult
    expected_exit_code: int


class SystemMoveFailureCase(NamedTuple):
    case_name: str
    system_move_hook_set: bool
    system_move_result: HookResult
    expected_exit_code: int


class TransitionCheckInvalidCase(NamedTuple):
    case_name: str
    to_state: str
    get_state_stdout: str
    describe_stdout: str
    count_stdout: str


DESCRIBE_VIEW = """states = ["Backlog", "In Progress", "In Work", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
"In Work" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""

CHAINED_DESCRIBE_VIEW = """states = ["Backlog", "In Progress", "In Work", "Done"]

[transitions]
Backlog = "In Progress"
"In Progress" = "In Work"
"In Work" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
"In Work" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""

AMBIGUOUS_DESCRIBE_VIEW = """states = ["Backlog", "In Progress", "In Work", "Done"]

[transitions]
"In Progress" = "In Work"
Backlog = "In Work"
"In Work" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
"In Progress" = {work = 3, wait = 2}
"In Work" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""

FIVE_STATE_CHAINED_DESCRIBE_VIEW = """states = ["Backlog", "Ready", "In Progress", "In Work", "Done"]

[transitions]
Backlog = "Ready"
Ready = "In Progress"
"In Progress" = "In Work"
"In Work" = "Done"

[wip_limits]
Backlog = {work = inf, wait = 3}
Ready = {work = 3, wait = 2}
"In Progress" = {work = 3, wait = 2}
"In Work" = {work = 3, wait = 2}
Done = {work = inf, wait = inf}
"""


def _happy_case_id(case: TransitionHappyCase) -> str:
    return case.case_name


def _unknown_state_case_id(case: TransitionUnknownStateCase) -> str:
    return case.case_name


def _hook_failure_case_id(case: TransitionHookFailureCase) -> str:
    return case.case_name


def _system_move_failure_case_id(case: SystemMoveFailureCase) -> str:
    return case.case_name


def _check_invalid_case_id(case: TransitionCheckInvalidCase) -> str:
    return case.case_name


def write_mock_get_state_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_get_state.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('Backlog\\n')\n"
    )
    return hook_command("mock_get_state.py")


def write_mock_describe_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_describe.py")
    hook.write_text(
        "import os, sys\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write(" + repr(DESCRIBE_VIEW) + ")\n"
    )
    return hook_command("mock_describe.py")


def write_mock_count_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_count.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'In Progress':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('wait = 1\\nwork = 3\\n')\n"
    )
    return hook_command("mock_count.py")


def write_mock_count_hook_below_work_limit(hook_command: HookCommand) -> str:
    hook = Path("mock_count.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_STATE') != 'In Progress':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_STATE'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('wait = 1\\nwork = 2\\n')\n"
    )
    return hook_command("mock_count.py")


def write_mock_system_move_hook(hook_command: HookCommand) -> str:
    hook = Path("mock_system_move.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        "if os.environ.get('WORKPULL_TO_STATE') != 'In Progress':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET', 'WORKPULL_TO_STATE'}:\n"
        "    sys.exit(1)\n"
        "sys.stdout.write('ticket-1\\n')\n"
    )
    return hook_command("mock_system_move.py")


def write_mock_hook(ticket_id: str, to_state: str, hook_command: HookCommand) -> str:
    hook = Path("mock_transition.py")
    hook.write_text(
        "import os, sys\n"
        "if os.environ.get('WORKPULL_TICKET') != 'ticket-1':\n"
        "    sys.exit(1)\n"
        f"if os.environ.get('WORKPULL_TO_STATE') != '{to_state}':\n"
        "    sys.exit(1)\n"
        "if os.environ.get('WORKPULL_TOKEN') != 'token-1':\n"
        "    sys.exit(1)\n"
        "if {key for key in os.environ if key.startswith('WORKPULL_')} != {'WORKPULL_TICKET', 'WORKPULL_TO_STATE', 'WORKPULL_TOKEN'}:\n"
        "    sys.exit(1)\n"
        f"sys.stdout.write('{ticket_id}\\n')\n"
    )
    return hook_command("mock_transition.py")


def transition_outcome(result: Result) -> TicketOutcome:
    outcome: TicketOutcome = {"exit_code": result.exit_code}
    if result.exit_code == 0:
        outcome["ticket_id"] = result.output.strip()
    else:
        outcome["ticket_id"] = None
    return outcome


@pytest.fixture
def run_transition(runner: CliRunner) -> RunTransition:
    def _run(
        ticket: str,
        to_state: str,
        token: str,
        env: dict[str, str],
        get_state_result: HookResult,
        describe_result: HookResult,
        count_result: HookResult,
        transition_result: HookResult,
        system_move_result: HookResult,
    ) -> TransitionRun:
        called_hooks: list[str] = []

        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            called_hooks.append(hook)
            if hook == env.get("GET_STATE_HOOK"):
                if hook_env != {"WORKPULL_TICKET": ticket}:
                    return HookResult(1, "", "")
                return get_state_result
            if hook == env.get("DESCRIBE_HOOK"):
                if hook_env != {}:
                    return HookResult(1, "", "")
                return describe_result
            if hook == env.get("COUNT_HOOK"):
                if hook_env != {"WORKPULL_STATE": to_state}:
                    return HookResult(1, "", "")
                return count_result
            if hook == env.get("TRANSITION_HOOK"):
                if hook_env != {
                    "WORKPULL_TICKET": ticket,
                    "WORKPULL_TO_STATE": to_state,
                    "WORKPULL_TOKEN": token,
                }:
                    return HookResult(1, "", "")
                return transition_result
            if hook == env.get("SYSTEM_MOVE_HOOK"):
                if hook_env != {
                    "WORKPULL_TICKET": transition_result.stdout.strip(),
                    "WORKPULL_TO_STATE": to_state,
                }:
                    return HookResult(1, "", "")
                return system_move_result
            return HookResult(1, "", "")

        result = runner.invoke(
            cli,
            ["transition", ticket, to_state, token],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )
        return TransitionRun(result=result, called_hooks=tuple(called_hooks))

    return _run


@pytest.mark.parametrize(
    "case",
    [
        TransitionHappyCase(
            case_name="ticket_1",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            ticket_id="ticket-1",
        ),
        TransitionHappyCase(
            case_name="ticket_0",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            ticket_id="0",
        ),
        TransitionHappyCase(
            case_name="inf_wait_limit",
            current_state="In Progress",
            to_state="Done",
            wait_count=99,
            ticket_id="ticket-1",
        ),
    ],
    ids=_happy_case_id,
)
def test_transition_happy_path(
    run_transition: RunTransition, case: TransitionHappyCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": case.ticket_id}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    run = run_transition(
        "ticket-1",
        case.to_state,
        "token-1",
        env,
        HookResult(0, f"{case.current_state}\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, f"wait = {case.wait_count}\nwork = 3\n", ""),
        HookResult(0, f"{case.ticket_id}\n", ""),
        HookResult(0, f"{case.ticket_id}\n", ""),
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def _case_id(case: TransitionCheckCase) -> str:
    return case.case_name


def _missing_hook_case_id(case: TransitionMissingHookCase) -> str:
    return case.case_name


def _failing_hook_case_id(case: TransitionFailingHookCase) -> str:
    return case.case_name


def _invalid_toml_case_id(case: TransitionInvalidTomlCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        TransitionCheckCase(
            case_name="false_unreachable",
            to_state="In Work",
            wait_count=1,
        ),
        TransitionCheckCase(
            case_name="false_at_limit",
            to_state="In Progress",
            wait_count=2,
        ),
    ],
    ids=_case_id,
)
def test_transition_check_is_false(
    run_transition: RunTransition, case: TransitionCheckCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    run = run_transition(
        "ticket-1",
        case.to_state,
        "token-1",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, f"wait = {case.wait_count}\nwork = 3\n", ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks


@pytest.mark.parametrize(
    "case",
    [
        TransitionMissingHookCase(
            case_name="missing_get_state_hook",
            missing_hook="GET_STATE_HOOK",
        ),
        TransitionMissingHookCase(
            case_name="missing_describe_hook",
            missing_hook="DESCRIBE_HOOK",
        ),
        TransitionMissingHookCase(
            case_name="missing_count_hook",
            missing_hook="COUNT_HOOK",
        ),
    ],
    ids=_missing_hook_case_id,
)
def test_transition_check_missing_hook(
    run_transition: RunTransition, case: TransitionMissingHookCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env.pop(case.missing_hook, None)
    run = run_transition(
        "ticket-1",
        "In Progress",
        "token-1",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks


@pytest.mark.parametrize(
    "case",
    [
        TransitionFailingHookCase(
            case_name="failing_get_state_hook",
            failing_hook="GET_STATE_HOOK",
        ),
        TransitionFailingHookCase(
            case_name="failing_describe_hook",
            failing_hook="DESCRIBE_HOOK",
        ),
        TransitionFailingHookCase(
            case_name="failing_count_hook",
            failing_hook="COUNT_HOOK",
        ),
    ],
    ids=_failing_hook_case_id,
)
def test_transition_check_failing_hook(
    run_transition: RunTransition, case: TransitionFailingHookCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    failing = HookResult(3, "", "")
    get_state_result = (
        failing if case.failing_hook == "GET_STATE_HOOK" else HookResult(0, "Backlog\n", "")
    )
    describe_result = (
        failing if case.failing_hook == "DESCRIBE_HOOK" else HookResult(0, DESCRIBE_VIEW, "")
    )
    count_result = (
        failing if case.failing_hook == "COUNT_HOOK" else HookResult(0, "wait = 1\nwork = 3\n", "")
    )
    run = run_transition(
        "ticket-1",
        "In Progress",
        "token-1",
        env,
        get_state_result,
        describe_result,
        count_result,
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks


@pytest.mark.parametrize(
    "case",
    [
        TransitionInvalidTomlCase(
            case_name="invalid_describe_toml",
            invalid_hook="DESCRIBE_HOOK",
        ),
        TransitionInvalidTomlCase(
            case_name="invalid_count_toml",
            invalid_hook="COUNT_HOOK",
        ),
    ],
    ids=_invalid_toml_case_id,
)
def test_transition_check_invalid_toml(
    run_transition: RunTransition, case: TransitionInvalidTomlCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    invalid = HookResult(0, "wait = \n", "")
    describe_result = (
        invalid if case.invalid_hook == "DESCRIBE_HOOK" else HookResult(0, DESCRIBE_VIEW, "")
    )
    count_result = (
        invalid if case.invalid_hook == "COUNT_HOOK" else HookResult(0, "wait = 1\nwork = 3\n", "")
    )
    run = run_transition(
        "ticket-1",
        "In Progress",
        "token-1",
        env,
        HookResult(0, "Backlog\n", ""),
        describe_result,
        count_result,
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks


@pytest.mark.parametrize(
    "case",
    [
        TransitionCheckInvalidCase(
            case_name="invalid_describe_output",
            to_state="Done",
            get_state_stdout="Backlog\n",
            describe_stdout="""states = ["Backlog", "Done"]

[transitions]
Backlog = "Backlog"

[wip_limits]
Backlog = {work = inf, wait = 3}
Done = {work = inf, wait = inf}
""",
            count_stdout="wait = 1\nwork = 3\n",
        ),
        TransitionCheckInvalidCase(
            case_name="empty_state",
            to_state="In Progress",
            get_state_stdout="",
            describe_stdout=DESCRIBE_VIEW,
            count_stdout="wait = 1\nwork = 3\n",
        ),
        TransitionCheckInvalidCase(
            case_name="invalid_count_output",
            to_state="In Progress",
            get_state_stdout="Backlog\n",
            describe_stdout=DESCRIBE_VIEW,
            count_stdout="work = 3\n",
        ),
    ],
    ids=_check_invalid_case_id,
)
def test_transition_check_invalid_output(
    run_transition: RunTransition, case: TransitionCheckInvalidCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    run = run_transition(
        "ticket-1",
        case.to_state,
        "token-1",
        env,
        HookResult(0, case.get_state_stdout, ""),
        HookResult(0, case.describe_stdout, ""),
        HookResult(0, case.count_stdout, ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks


@pytest.mark.parametrize(
    "case",
    [
        TransitionUnknownStateCase(
            case_name="unknown_to_state",
            to_state="Unknown",
            current_state="Backlog",
            count_called=False,
        ),
        TransitionUnknownStateCase(
            case_name="unknown_current_state",
            to_state="In Progress",
            current_state="Unknown",
            count_called=True,
        ),
    ],
    ids=_unknown_state_case_id,
)
def test_transition_check_unknown_state(
    run_transition: RunTransition, case: TransitionUnknownStateCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    run = run_transition(
        "ticket-1",
        case.to_state,
        "token-1",
        env,
        HookResult(0, f"{case.current_state}\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert "fake-transition" not in run.called_hooks
    assert ("fake-count" in run.called_hooks) == case.count_called


class SystemMoveHappyCase(NamedTuple):
    case_name: str
    current_state: str
    to_state: str
    wait_count: int
    work_count: int
    ticket_id: str
    system_move_called: bool


def _system_move_happy_case_id(case: SystemMoveHappyCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        SystemMoveHappyCase(
            case_name="capacity_available",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            work_count=2,
            ticket_id="ticket-1",
            system_move_called=True,
        ),
        SystemMoveHappyCase(
            case_name="no_capacity_at_limit",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            work_count=3,
            ticket_id="ticket-1",
            system_move_called=False,
        ),
        SystemMoveHappyCase(
            case_name="inf_work_limit",
            current_state="In Progress",
            to_state="Done",
            wait_count=1,
            work_count=99,
            ticket_id="ticket-1",
            system_move_called=True,
        ),
        SystemMoveHappyCase(
            case_name="ticket_0",
            current_state="Backlog",
            to_state="In Progress",
            wait_count=1,
            work_count=2,
            ticket_id="0",
            system_move_called=True,
        ),
    ],
    ids=_system_move_happy_case_id,
)
def test_transition_system_move(
    run_transition: RunTransition, case: SystemMoveHappyCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": case.ticket_id}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    run = run_transition(
        "ticket-1",
        case.to_state,
        "token-1",
        env,
        HookResult(0, f"{case.current_state}\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, f"wait = {case.wait_count}\nwork = {case.work_count}\n", ""),
        HookResult(0, f"{case.ticket_id}\n", ""),
        HookResult(0, f"{case.ticket_id}\n", ""),
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert run.called_hooks.count("fake-system-move") == (
        1 if case.system_move_called else 0
    )
    assert run.called_hooks.count("fake-get-state") == 1
    assert run.called_hooks.count("fake-transition") == 1
    assert run.called_hooks.count("fake-count") == 1
    assert run.called_hooks.count("fake-describe") == 1


@pytest.mark.parametrize(
    "case",
    [
        SystemMoveFailureCase(
            case_name="missing_hook",
            system_move_hook_set=False,
            system_move_result=HookResult(0, "ticket-1\n", ""),
            expected_exit_code=2,
        ),
        SystemMoveFailureCase(
            case_name="failing_hook",
            system_move_hook_set=True,
            system_move_result=HookResult(3, "", ""),
            expected_exit_code=3,
        ),
        SystemMoveFailureCase(
            case_name="empty_ticket_id",
            system_move_hook_set=True,
            system_move_result=HookResult(0, "", ""),
            expected_exit_code=2,
        ),
    ],
    ids=_system_move_failure_case_id,
)
def test_transition_system_move_failure(
    run_transition: RunTransition, case: SystemMoveFailureCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {
        "exit_code": case.expected_exit_code,
        "ticket_id": None,
    }
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    if case.system_move_hook_set:
        env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    else:
        env.pop("SYSTEM_MOVE_HOOK", None)
    run = run_transition(
        "ticket-1",
        "In Progress",
        "token-1",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 2\n", ""),
        HookResult(0, "ticket-1\n", ""),
        case.system_move_result,
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_system_move_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        get_state_hook = write_mock_get_state_hook(hook_command)
        describe_hook = write_mock_describe_hook(hook_command)
        count_hook = write_mock_count_hook_below_work_limit(hook_command)
        hook = write_mock_hook("ticket-1", "In Progress", hook_command)
        system_move_hook = write_mock_system_move_hook(hook_command)
        env = dict(os.environ)
        env["GET_STATE_HOOK"] = get_state_hook
        env["DESCRIBE_HOOK"] = describe_hook
        env["COUNT_HOOK"] = count_hook
        env["TRANSITION_HOOK"] = hook
        env["SYSTEM_MOVE_HOOK"] = system_move_hook
        result = runner.invoke(
            cli, ["transition", "ticket-1", "In Progress", "token-1"], env=env, obj={}
        )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_real_hook(runner: CliRunner, isolated_filesystem: IsolatedFilesystem, hook_command: HookCommand) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-1"}
    # WHEN
    with isolated_filesystem():
        get_state_hook = write_mock_get_state_hook(hook_command)
        describe_hook = write_mock_describe_hook(hook_command)
        count_hook = write_mock_count_hook(hook_command)
        hook = write_mock_hook("ticket-1", "In Progress", hook_command)
        env = dict(os.environ)
        env["GET_STATE_HOOK"] = get_state_hook
        env["DESCRIBE_HOOK"] = describe_hook
        env["COUNT_HOOK"] = count_hook
        env["TRANSITION_HOOK"] = hook
        result = runner.invoke(
            cli, ["transition", "ticket-1", "In Progress", "token-1"], env=env, obj={}
        )
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


@pytest.mark.parametrize(
    "case",
    [
        TransitionHookFailureCase(
            case_name="missing_hook",
            transition_hook_set=False,
            transition_result=HookResult(0, "ticket-1\n", ""),
            expected_exit_code=2,
        ),
        TransitionHookFailureCase(
            case_name="failing_hook",
            transition_hook_set=True,
            transition_result=HookResult(3, "", ""),
            expected_exit_code=3,
        ),
        TransitionHookFailureCase(
            case_name="empty_ticket_id",
            transition_hook_set=True,
            transition_result=HookResult(0, "", ""),
            expected_exit_code=2,
        ),
    ],
    ids=_hook_failure_case_id,
)
def test_transition_hook_failure(
    run_transition: RunTransition, case: TransitionHookFailureCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {
        "exit_code": case.expected_exit_code,
        "ticket_id": None,
    }
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    if case.transition_hook_set:
        env["TRANSITION_HOOK"] = "fake-transition"
    else:
        env.pop("TRANSITION_HOOK", None)
    run = run_transition(
        "ticket-1",
        "In Progress",
        "token-1",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
        case.transition_result,
        HookResult(0, "ticket-1\n", ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual


def test_transition_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help(
            """Usage: cli transition [OPTIONS] TICKET TO_STATE TOKEN

            Move a ticket to a wait state.

            Options:
              --help  Show this message and exit.
            """
        ),
    }
    # WHEN
    result = runner.invoke(cli, ["transition", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual


class PullRun(NamedTuple):
    result: Result
    called_hooks: tuple[str, ...]


# A hook call the test never expects: exit 1, no output.
# Any fake branch that returns this is a guard, not a stub.
UNEXPECTED_HOOK_CALL = HookResult(1, "", "")

# No cascade ticket is expected in a single-step test.
NO_CASCADE_TICKET = ""


class SystemMoveCall(NamedTuple):
    ticket: str
    to_state: str


# One cascade step: the pull into one predecessor state.
# A cascade is a tuple of these, one per step, so a test
# can chain as many steps as its describe view has states.
class CascadeStepResults(NamedTuple):
    state: str
    count_result: HookResult
    list_waiting_result: HookResult
    pulled_ticket: str
    system_move_result: HookResult


def _run_transition(
    runner: CliRunner,
    ticket: str,
    to_state: str,
    token: str,
    old_state: str,
    pull_ticket: str,
    env: dict[str, str],
    get_state_result: HookResult,
    describe_result: HookResult,
    count_to_result: HookResult,
    count_old_result: HookResult,
    transition_result: HookResult,
    system_move_result: HookResult,
    pull_system_move_result: HookResult,
    list_waiting_result: HookResult,
    cascade_steps: tuple[CascadeStepResults, ...],
) -> PullRun:
    called_hooks: list[str] = []
    count_results: dict[str, HookResult] = {
        to_state: count_to_result,
        old_state: count_old_result,
    }
    list_waiting_results: dict[str, HookResult] = {
        old_state: list_waiting_result,
    }
    system_move_results: dict[SystemMoveCall, HookResult] = {
        SystemMoveCall(
            ticket=transition_result.stdout.strip(), to_state=to_state
        ): system_move_result,
        SystemMoveCall(
            ticket=pull_ticket, to_state=old_state
        ): pull_system_move_result,
    }
    for step in cascade_steps:
        count_results[step.state] = step.count_result
        list_waiting_results[step.state] = step.list_waiting_result
        system_move_results[
            SystemMoveCall(ticket=step.pulled_ticket, to_state=step.state)
        ] = step.system_move_result

    def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
        called_hooks.append(hook)
        if hook == env.get("GET_STATE_HOOK"):
            if hook_env != {"WORKPULL_TICKET": ticket}:
                return UNEXPECTED_HOOK_CALL
            return get_state_result
        if hook == env.get("DESCRIBE_HOOK"):
            if hook_env != {}:
                return UNEXPECTED_HOOK_CALL
            return describe_result
        if hook == env.get("COUNT_HOOK"):
            if set(hook_env) != {"WORKPULL_STATE"}:
                return UNEXPECTED_HOOK_CALL
            return count_results.get(
                hook_env["WORKPULL_STATE"], UNEXPECTED_HOOK_CALL
            )
        if hook == env.get("TRANSITION_HOOK"):
            if hook_env != {
                "WORKPULL_TICKET": ticket,
                "WORKPULL_TO_STATE": to_state,
                "WORKPULL_TOKEN": token,
            }:
                return UNEXPECTED_HOOK_CALL
            return transition_result
        if hook == env.get("SYSTEM_MOVE_HOOK"):
            if set(hook_env) != {"WORKPULL_TICKET", "WORKPULL_TO_STATE"}:
                return UNEXPECTED_HOOK_CALL
            return system_move_results.get(
                SystemMoveCall(
                    ticket=hook_env["WORKPULL_TICKET"],
                    to_state=hook_env["WORKPULL_TO_STATE"],
                ),
                UNEXPECTED_HOOK_CALL,
            )
        if hook == env.get("LIST_WAITING_HOOK"):
            if set(hook_env) != {"WORKPULL_STATE"}:
                return UNEXPECTED_HOOK_CALL
            return list_waiting_results.get(
                hook_env["WORKPULL_STATE"], UNEXPECTED_HOOK_CALL
            )
        return UNEXPECTED_HOOK_CALL

    result = runner.invoke(
        cli,
        ["transition", ticket, to_state, token],
        env=env,
        obj={"run_hook": _fake_run_hook},
    )
    return PullRun(result=result, called_hooks=tuple(called_hooks))


RunTransitionPull = Callable[
    [
        str,
        str,
        str,
        str,
        str,
        dict[str, str],
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
    ],
    PullRun,
]


RunTransitionCascade = Callable[
    [
        str,
        str,
        str,
        str,
        str,
        dict[str, str],
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        str,
        HookResult,
        HookResult,
        str,
        HookResult,
    ],
    PullRun,
]


@pytest.fixture
def run_transition_pull(runner: CliRunner) -> RunTransitionPull:
    def _run(
        ticket: str,
        to_state: str,
        token: str,
        old_state: str,
        pull_ticket: str,
        env: dict[str, str],
        get_state_result: HookResult,
        describe_result: HookResult,
        count_to_result: HookResult,
        count_old_result: HookResult,
        transition_result: HookResult,
        system_move_result: HookResult,
        pull_system_move_result: HookResult,
        list_waiting_result: HookResult,
    ) -> PullRun:
        return _run_transition(
            runner,
            ticket,
            to_state,
            token,
            old_state,
            pull_ticket,
            env,
            get_state_result,
            describe_result,
            count_to_result,
            count_old_result,
            transition_result,
            system_move_result,
            pull_system_move_result,
            list_waiting_result,
            (),
        )

    return _run


@pytest.fixture
def run_transition_cascade(runner: CliRunner) -> RunTransitionCascade:
    def _run(
        ticket: str,
        to_state: str,
        token: str,
        old_state: str,
        pull_ticket: str,
        env: dict[str, str],
        get_state_result: HookResult,
        describe_result: HookResult,
        count_to_result: HookResult,
        count_old_result: HookResult,
        transition_result: HookResult,
        system_move_result: HookResult,
        pull_system_move_result: HookResult,
        list_waiting_result: HookResult,
        predecessor_state: str,
        count_predecessor_result: HookResult,
        list_waiting_predecessor_result: HookResult,
        cascade_ticket: str,
        cascade_system_move_result: HookResult,
    ) -> PullRun:
        return _run_transition(
            runner,
            ticket,
            to_state,
            token,
            old_state,
            pull_ticket,
            env,
            get_state_result,
            describe_result,
            count_to_result,
            count_old_result,
            transition_result,
            system_move_result,
            pull_system_move_result,
            list_waiting_result,
            (
                CascadeStepResults(
                    state=predecessor_state,
                    count_result=count_predecessor_result,
                    list_waiting_result=list_waiting_predecessor_result,
                    pulled_ticket=cascade_ticket,
                    system_move_result=cascade_system_move_result,
                ),
            ),
        )

    return _run


RunTransitionChain = Callable[
    [
        str,
        str,
        str,
        str,
        str,
        dict[str, str],
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        HookResult,
        tuple[CascadeStepResults, ...],
    ],
    PullRun,
]


@pytest.fixture
def run_transition_chain(runner: CliRunner) -> RunTransitionChain:
    def _run(
        ticket: str,
        to_state: str,
        token: str,
        old_state: str,
        pull_ticket: str,
        env: dict[str, str],
        get_state_result: HookResult,
        describe_result: HookResult,
        count_to_result: HookResult,
        count_old_result: HookResult,
        transition_result: HookResult,
        system_move_result: HookResult,
        pull_system_move_result: HookResult,
        list_waiting_result: HookResult,
        cascade_steps: tuple[CascadeStepResults, ...],
    ) -> PullRun:
        return _run_transition(
            runner,
            ticket,
            to_state,
            token,
            old_state,
            pull_ticket,
            env,
            get_state_result,
            describe_result,
            count_to_result,
            count_old_result,
            transition_result,
            system_move_result,
            pull_system_move_result,
            list_waiting_result,
            cascade_steps,
        )

    return _run


class ListWaitingFailureCase(NamedTuple):
    case_name: str
    list_waiting_result: HookResult
    expected_exit_code: int
    expected_output: str


def _list_waiting_failure_case_id(case: ListWaitingFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ListWaitingFailureCase(
            case_name="failing_hook",
            list_waiting_result=HookResult(3, "", ""),
            expected_exit_code=3,
            expected_output="",
        ),
        ListWaitingFailureCase(
            case_name="invalid_toml",
            list_waiting_result=HookResult(0, "wait = \n", ""),
            expected_exit_code=2,
            expected_output="list-waiting hook output is not valid TOML: Invalid value (at line 1, column 8)\n",
        ),
        ListWaitingFailureCase(
            case_name="wrong_shape",
            list_waiting_result=HookResult(0, 'tickets = "ticket-3"\n', ""),
            expected_exit_code=2,
            expected_output="invalid list-waiting output: expected tickets\n",
        ),
        ListWaitingFailureCase(
            case_name="empty_ticket",
            list_waiting_result=HookResult(0, 'tickets = [""]\n', ""),
            expected_exit_code=2,
            expected_output="invalid list-waiting output: expected tickets\n",
        ),
        ListWaitingFailureCase(
            case_name="non_string_ticket",
            list_waiting_result=HookResult(0, "tickets = [1]\n", ""),
            expected_exit_code=2,
            expected_output="invalid list-waiting output: expected tickets\n",
        ),
        ListWaitingFailureCase(
            case_name="extra_key",
            list_waiting_result=HookResult(0, 'tickets = ["ticket-3"]\nextra = 1\n', ""),
            expected_exit_code=2,
            expected_output="invalid list-waiting output: expected tickets\n",
        ),
    ],
    ids=_list_waiting_failure_case_id,
)
def test_transition_pull_list_waiting_failure(
    run_transition_pull: RunTransitionPull, case: ListWaitingFailureCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": case.expected_exit_code, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_pull(
        "ticket-2",
        "Done",
        "token-1",
        "In Progress",
        "ticket-3",
        env,
        HookResult(0, "In Progress\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        case.list_waiting_result,
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert result.output == case.expected_output
    assert "fake-list-waiting" in run.called_hooks
    assert run.called_hooks.count("fake-system-move") == 1


def test_transition_pull_count_failure(
    run_transition_pull: RunTransitionPull,
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 3, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_pull(
        "ticket-2",
        "Done",
        "token-1",
        "In Progress",
        "ticket-3",
        env,
        HookResult(0, "In Progress\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(3, "", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert result.output == ""
    assert "fake-list-waiting" not in run.called_hooks
    assert run.called_hooks.count("fake-system-move") == 1


class PullEarlyReturnCase(NamedTuple):
    case_name: str
    count_old_result: HookResult
    list_waiting_result: HookResult
    expected_list_calls: int
    expected_system_move_calls: int


def _pull_early_return_case_id(case: PullEarlyReturnCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullEarlyReturnCase(
            case_name="no_capacity",
            count_old_result=HookResult(0, "wait = 1\nwork = 3\n", ""),
            list_waiting_result=HookResult(0, 'tickets = ["ticket-3"]\n', ""),
            expected_list_calls=0,
            expected_system_move_calls=1,
        ),
        PullEarlyReturnCase(
            case_name="empty_waiting_list",
            count_old_result=HookResult(0, "wait = 0\nwork = 0\n", ""),
            list_waiting_result=HookResult(0, "tickets = []\n", ""),
            expected_list_calls=1,
            expected_system_move_calls=1,
        ),
    ],
    ids=_pull_early_return_case_id,
)
def test_transition_pull_early_return(
    run_transition_pull: RunTransitionPull, case: PullEarlyReturnCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-2"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_pull(
        "ticket-2",
        "Done",
        "token-1",
        "In Progress",
        "ticket-3",
        env,
        HookResult(0, "In Progress\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        case.count_old_result,
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        case.list_waiting_result,
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert run.called_hooks.count("fake-list-waiting") == case.expected_list_calls
    assert run.called_hooks.count("fake-system-move") == case.expected_system_move_calls


class PullTransitionCase(NamedTuple):
    case_name: str
    ticket: str
    to_state: str
    old_state: str
    pull_ticket: str
    get_state_stdout: str
    count_to_result: HookResult
    count_old_result: HookResult
    count_old_work_tickets: tuple[str, ...]
    count_old_wait_tickets: tuple[str, ...]
    list_waiting_result: HookResult
    expected_system_move_calls: int
    predecessor_state: str
    count_predecessor_result: HookResult
    list_waiting_predecessor_result: HookResult
    expected_count_calls: int
    expected_list_calls: int


def _pull_transition_case_id(case: PullTransitionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullTransitionCase(
            case_name="single_waiting_ticket",
            ticket="ticket-2",
            to_state="Done",
            old_state="In Progress",
            pull_ticket="ticket-3",
            get_state_stdout="In Progress\n",
            count_to_result=HookResult(0, "wait = 0\nwork = 0\n", ""),
            count_old_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
            count_old_work_tickets=(),
            count_old_wait_tickets=("ticket-3",),
            list_waiting_result=HookResult(0, 'tickets = ["ticket-3"]\n', ""),
            expected_system_move_calls=2,
            predecessor_state="Backlog",
            count_predecessor_result=HookResult(0, "wait = 0\nwork = 0\n", ""),
            list_waiting_predecessor_result=HookResult(
                0, "tickets = []\n", ""
            ),
            expected_count_calls=3,
            expected_list_calls=2,
        ),
        PullTransitionCase(
            case_name="highest_priority_of_two_waiting_tickets",
            ticket="ticket-2",
            to_state="Done",
            old_state="In Progress",
            pull_ticket="ticket-3",
            get_state_stdout="In Progress\n",
            count_to_result=HookResult(0, "wait = 0\nwork = 0\n", ""),
            count_old_result=HookResult(0, "wait = 2\nwork = 0\n", ""),
            count_old_work_tickets=(),
            count_old_wait_tickets=("ticket-3", "ticket-4"),
            list_waiting_result=HookResult(
                0, 'tickets = ["ticket-3", "ticket-4"]\n', ""
            ),
            expected_system_move_calls=2,
            predecessor_state="Backlog",
            # Ticket-4 still counts as Backlog work while it
            # waits for In Progress, so work is 1 here.
            count_predecessor_result=HookResult(0, "wait = 0\nwork = 1\n", ""),
            list_waiting_predecessor_result=HookResult(
                0, "tickets = []\n", ""
            ),
            expected_count_calls=3,
            expected_list_calls=2,
        ),
        PullTransitionCase(
            case_name="after_event_9",
            ticket="ticket-1",
            to_state="In Progress",
            old_state="Backlog",
            pull_ticket="ticket-3",
            get_state_stdout="Backlog\n",
            count_to_result=HookResult(0, "wait = 1\nwork = 3\n", ""),
            count_old_result=HookResult(0, "wait = 1\nwork = 2\n", ""),
            count_old_work_tickets=("ticket-1", "ticket-3"),
            count_old_wait_tickets=("ticket-3",),
            list_waiting_result=HookResult(0, 'tickets = ["ticket-3"]\n', ""),
            expected_system_move_calls=1,
            # Backlog has no predecessor, so no second pull
            # runs and these results are never consumed.
            predecessor_state="",
            count_predecessor_result=HookResult(0, "wait = 0\nwork = 0\n", ""),
            list_waiting_predecessor_result=HookResult(
                0, "tickets = []\n", ""
            ),
            expected_count_calls=2,
            expected_list_calls=1,
        ),
    ],
    ids=_pull_transition_case_id,
)
def test_transition_pull(
    run_transition_cascade: RunTransitionCascade, case: PullTransitionCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": case.ticket}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_cascade(
        case.ticket,
        case.to_state,
        "token-1",
        case.old_state,
        case.pull_ticket,
        env,
        HookResult(0, case.get_state_stdout, ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        case.count_to_result,
        case.count_old_result,
        HookResult(0, f"{case.ticket}\n", ""),
        HookResult(0, f"{case.ticket}\n", ""),
        HookResult(0, f"{case.pull_ticket}\n", ""),
        case.list_waiting_result,
        case.predecessor_state,
        case.count_predecessor_result,
        case.list_waiting_predecessor_result,
        NO_CASCADE_TICKET,
        UNEXPECTED_HOOK_CALL,
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert case.count_old_result.stdout == (
        f"wait = {len(case.count_old_wait_tickets)}\n"
        f"work = {len(case.count_old_work_tickets)}\n"
    )
    assert run.called_hooks.count("fake-list-waiting") == case.expected_list_calls
    assert run.called_hooks.count("fake-system-move") == case.expected_system_move_calls
    assert run.called_hooks.count("fake-get-state") == 1
    assert run.called_hooks.count("fake-transition") == 1
    assert run.called_hooks.count("fake-count") == case.expected_count_calls
    assert run.called_hooks.count("fake-describe") == 1


class PullSystemMoveFailureCase(NamedTuple):
    case_name: str
    pull_system_move_result: HookResult
    expected_exit_code: int
    expected_output: str


def _pull_system_move_failure_case_id(case: PullSystemMoveFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullSystemMoveFailureCase(
            case_name="failing_hook",
            pull_system_move_result=HookResult(3, "", ""),
            expected_exit_code=3,
            expected_output="",
        ),
        PullSystemMoveFailureCase(
            case_name="empty_ticket_id",
            pull_system_move_result=HookResult(0, "", ""),
            expected_exit_code=2,
            expected_output="system move hook returned no ticket id\n",
        ),
    ],
    ids=_pull_system_move_failure_case_id,
)
def test_transition_pull_system_move_failure(
    run_transition_pull: RunTransitionPull, case: PullSystemMoveFailureCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": case.expected_exit_code, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_pull(
        "ticket-2",
        "Done",
        "token-1",
        "In Progress",
        "ticket-3",
        env,
        HookResult(0, "In Progress\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        case.pull_system_move_result,
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert result.output == case.expected_output
    assert run.called_hooks.count("fake-list-waiting") == 1
    assert run.called_hooks.count("fake-system-move") == 2


def test_transition_pull_system_move_missing_hook_after_event_9(
    run_transition_pull: RunTransitionPull,
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 2, "ticket_id": None}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env.pop("SYSTEM_MOVE_HOOK", None)
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_pull(
        "ticket-1",
        "In Progress",
        "token-1",
        "Backlog",
        "ticket-3",
        env,
        HookResult(0, "Backlog\n", ""),
        HookResult(0, DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 1\nwork = 3\n", ""),
        # Backlog after Event 9: work is ticket-1, still in
        # Backlog waiting for In Progress, and ticket-3, in
        # Backlog waiting for Backlog; wait is ticket-3.
        HookResult(0, "wait = 1\nwork = 2\n", ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-1\n", ""),
        HookResult(0, "ticket-3\n", ""),
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert result.output == "SYSTEM_MOVE_HOOK is not set\n"
    assert run.called_hooks.count("fake-list-waiting") == 1
    assert "fake-system-move" not in run.called_hooks


def test_transition_cascade_ambiguous_predecessor_first_in_states_order(
    run_transition_cascade: RunTransitionCascade,
) -> None:
    # GIVEN
    # Backlog and In Progress both transition to In Work.
    # The transitions table lists In Progress first, but
    # Backlog is first in the states list, so the second
    # pull goes to Backlog, not In Progress. Backlog has
    # no predecessor, so the cascade stops there, and the
    # hook counts pin that no third pull runs.
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-2"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_cascade(
        "ticket-2",
        "Done",
        "token-1",
        "In Work",
        "ticket-3",
        env,
        HookResult(0, "In Work\n", ""),
        HookResult(0, AMBIGUOUS_DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
        "Backlog",
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, 'tickets = ["ticket-4"]\n', ""),
        "ticket-4",
        HookResult(0, "ticket-4\n", ""),
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert run.called_hooks.count("fake-list-waiting") == 2
    assert run.called_hooks.count("fake-system-move") == 3
    assert run.called_hooks.count("fake-get-state") == 1
    assert run.called_hooks.count("fake-transition") == 1
    assert run.called_hooks.count("fake-count") == 3
    assert run.called_hooks.count("fake-describe") == 1


class CascadeChainCase(NamedTuple):
    case_name: str
    describe_result: HookResult
    cascade_steps: tuple[CascadeStepResults, ...]
    expected_count_calls: int
    expected_list_calls: int
    expected_system_move_calls: int


def _cascade_chain_case_id(case: CascadeChainCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        CascadeChainCase(
            case_name="three_steps",
            describe_result=HookResult(0, CHAINED_DESCRIBE_VIEW, ""),
            cascade_steps=(
                CascadeStepResults(
                    state="In Progress",
                    count_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
                    list_waiting_result=HookResult(
                        0, 'tickets = ["ticket-4"]\n', ""
                    ),
                    pulled_ticket="ticket-4",
                    system_move_result=HookResult(0, "ticket-4\n", ""),
                ),
                CascadeStepResults(
                    state="Backlog",
                    count_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
                    list_waiting_result=HookResult(
                        0, 'tickets = ["ticket-5"]\n', ""
                    ),
                    pulled_ticket="ticket-5",
                    system_move_result=HookResult(0, "ticket-5\n", ""),
                ),
            ),
            expected_count_calls=4,
            expected_list_calls=3,
            expected_system_move_calls=4,
        ),
        CascadeChainCase(
            case_name="four_steps",
            describe_result=HookResult(0, FIVE_STATE_CHAINED_DESCRIBE_VIEW, ""),
            cascade_steps=(
                CascadeStepResults(
                    state="In Progress",
                    count_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
                    list_waiting_result=HookResult(
                        0, 'tickets = ["ticket-4"]\n', ""
                    ),
                    pulled_ticket="ticket-4",
                    system_move_result=HookResult(0, "ticket-4\n", ""),
                ),
                CascadeStepResults(
                    state="Ready",
                    count_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
                    list_waiting_result=HookResult(
                        0, 'tickets = ["ticket-5"]\n', ""
                    ),
                    pulled_ticket="ticket-5",
                    system_move_result=HookResult(0, "ticket-5\n", ""),
                ),
                CascadeStepResults(
                    state="Backlog",
                    count_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
                    list_waiting_result=HookResult(
                        0, 'tickets = ["ticket-6"]\n', ""
                    ),
                    pulled_ticket="ticket-6",
                    system_move_result=HookResult(0, "ticket-6\n", ""),
                ),
            ),
            expected_count_calls=5,
            expected_list_calls=4,
            expected_system_move_calls=5,
        ),
    ],
    ids=_cascade_chain_case_id,
)
def test_transition_cascade_pulls_backwards_n_steps(
    run_transition_chain: RunTransitionChain, case: CascadeChainCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {"exit_code": 0, "ticket_id": "ticket-2"}
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_chain(
        "ticket-2",
        "Done",
        "token-1",
        "In Work",
        "ticket-3",
        env,
        HookResult(0, "In Work\n", ""),
        case.describe_result,
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
        case.cascade_steps,
    )
    result = run.result
    # THEN
    assert result.exception is None
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert run.called_hooks.count("fake-list-waiting") == case.expected_list_calls
    assert (
        run.called_hooks.count("fake-system-move")
        == case.expected_system_move_calls
    )
    assert run.called_hooks.count("fake-get-state") == 1
    assert run.called_hooks.count("fake-transition") == 1
    assert run.called_hooks.count("fake-count") == case.expected_count_calls
    assert run.called_hooks.count("fake-describe") == 1


class CascadeFailureCase(NamedTuple):
    case_name: str
    count_cascade_result: HookResult
    list_waiting_cascade_result: HookResult
    cascade_system_move_result: HookResult
    expected_exit_code: int
    expected_output: str
    expected_list_calls: int
    expected_system_move_calls: int


def _cascade_failure_case_id(case: CascadeFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        CascadeFailureCase(
            case_name="cascade_count_at_limit",
            count_cascade_result=HookResult(0, "wait = 1\nwork = 3\n", ""),
            list_waiting_cascade_result=HookResult(
                0, 'tickets = ["ticket-4"]\n', ""
            ),
            cascade_system_move_result=HookResult(0, "ticket-4\n", ""),
            expected_exit_code=0,
            expected_output="ticket-2\n",
            expected_list_calls=1,
            expected_system_move_calls=2,
        ),
        CascadeFailureCase(
            case_name="cascade_list_waiting_failing",
            count_cascade_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
            list_waiting_cascade_result=HookResult(3, "", ""),
            cascade_system_move_result=HookResult(0, "ticket-4\n", ""),
            expected_exit_code=3,
            expected_output="",
            expected_list_calls=2,
            expected_system_move_calls=2,
        ),
        CascadeFailureCase(
            case_name="cascade_system_move_failing",
            count_cascade_result=HookResult(0, "wait = 1\nwork = 0\n", ""),
            list_waiting_cascade_result=HookResult(
                0, 'tickets = ["ticket-4"]\n', ""
            ),
            cascade_system_move_result=HookResult(3, "", ""),
            expected_exit_code=3,
            expected_output="",
            expected_list_calls=2,
            expected_system_move_calls=3,
        ),
    ],
    ids=_cascade_failure_case_id,
)
def test_transition_cascade_failure(
    run_transition_cascade: RunTransitionCascade, case: CascadeFailureCase
) -> None:
    # GIVEN
    expected: TicketOutcome = {
        "exit_code": case.expected_exit_code,
        "ticket_id": "ticket-2" if case.expected_exit_code == 0 else None,
    }
    # WHEN
    env = dict(os.environ)
    env["GET_STATE_HOOK"] = "fake-get-state"
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["TRANSITION_HOOK"] = "fake-transition"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    run = run_transition_cascade(
        "ticket-2",
        "Done",
        "token-1",
        "In Work",
        "ticket-3",
        env,
        HookResult(0, "In Work\n", ""),
        HookResult(0, CHAINED_DESCRIBE_VIEW, ""),
        HookResult(0, "wait = 0\nwork = 0\n", ""),
        HookResult(0, "wait = 1\nwork = 0\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-2\n", ""),
        HookResult(0, "ticket-3\n", ""),
        HookResult(0, 'tickets = ["ticket-3"]\n', ""),
        "In Progress",
        case.count_cascade_result,
        case.list_waiting_cascade_result,
        "ticket-4",
        case.cascade_system_move_result,
    )
    result = run.result
    # THEN
    actual: TicketOutcome = transition_outcome(result)
    assert expected == actual
    assert result.output == case.expected_output
    assert run.called_hooks.count("fake-list-waiting") == case.expected_list_calls
    assert (
        run.called_hooks.count("fake-system-move")
        == case.expected_system_move_calls
    )
    assert run.called_hooks.count("fake-get-state") == 1
    assert run.called_hooks.count("fake-transition") == 1
    assert run.called_hooks.count("fake-count") == 3
    assert run.called_hooks.count("fake-describe") == 1
