"""Tests for workpull pull, through Click's runner."""

import json
import os
from pathlib import Path
from typing import NamedTuple, TypedDict

import contextlib

import pytest
from click.testing import CliRunner, Result
from collections.abc import Callable

from workpull.cli import HookResult, cli

IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]
NormalizeHelp = Callable[[str], str]


class PullOutcome(TypedDict, total=False):
    exit_code: int
    output: str


class HelpOutcome(TypedDict, total=False):
    exit_code: int
    help_text: str


class FakeTicket(NamedTuple):
    ticket_id: str
    state: str
    priority: str
    waiting_for: str | None


class PullRun(NamedTuple):
    result: Result
    called_hooks: tuple[str, ...]
    tickets: tuple[FakeTicket, ...]


RunPull = Callable[
    [dict[str, str], tuple[FakeTicket, ...], dict[str, HookResult]],
    PullRun,
]


DESCRIBE_VIEW = """states = ["Backlog", "In Progress", "In Work", "Done"]

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

# A hook call the test never expects: exit 1, no output.
# Any fake branch that returns this is a guard, not a stub.
UNEXPECTED_HOOK_CALL = HookResult(1, "", "")


def pull_outcome(result: Result) -> PullOutcome:
    return {"exit_code": result.exit_code, "output": result.output}


def pull_env() -> dict[str, str]:
    env = dict(os.environ)
    env["DESCRIBE_HOOK"] = "fake-describe"
    env["COUNT_HOOK"] = "fake-count"
    env["LIST_WAITING_HOOK"] = "fake-list-waiting"
    env["SYSTEM_MOVE_HOOK"] = "fake-system-move"
    return env


@pytest.fixture
def run_pull(runner: CliRunner) -> RunPull:
    def _run(
        env: dict[str, str],
        tickets: tuple[FakeTicket, ...],
        overrides: dict[str, HookResult],
    ) -> PullRun:
        board = list(tickets)
        called_hooks: list[str] = []

        def _fake_run_hook(hook: str, hook_env: dict[str, str]) -> HookResult:
            called_hooks.append(hook)
            if hook == env.get("DESCRIBE_HOOK"):
                if hook_env != {}:
                    return UNEXPECTED_HOOK_CALL
                return overrides.get("describe", HookResult(0, DESCRIBE_VIEW, ""))
            if hook == env.get("COUNT_HOOK"):
                if set(hook_env) != {"WORKPULL_STATE"}:
                    return UNEXPECTED_HOOK_CALL
                state = hook_env["WORKPULL_STATE"]
                if f"count:{state}" in overrides:
                    return overrides[f"count:{state}"]
                work = sum(1 for ticket in board if ticket.state == state)
                wait = sum(1 for ticket in board if ticket.waiting_for == state)
                return HookResult(0, f"wait = {wait}\nwork = {work}\n", "")
            if hook == env.get("LIST_WAITING_HOOK"):
                if set(hook_env) != {"WORKPULL_STATE"}:
                    return UNEXPECTED_HOOK_CALL
                state = hook_env["WORKPULL_STATE"]
                if f"list-waiting:{state}" in overrides:
                    return overrides[f"list-waiting:{state}"]
                waiting = sorted(
                    (ticket for ticket in board if ticket.waiting_for == state),
                    key=lambda ticket: ticket.priority,
                )
                names = ", ".join(f'"{ticket.ticket_id}"' for ticket in waiting)
                return HookResult(0, f"tickets = [{names}]\n", "")
            if hook == env.get("SYSTEM_MOVE_HOOK"):
                if set(hook_env) != {"WORKPULL_TICKET", "WORKPULL_TO_STATE"}:
                    return UNEXPECTED_HOOK_CALL
                ticket_id = hook_env["WORKPULL_TICKET"]
                to_state = hook_env["WORKPULL_TO_STATE"]
                if f"system-move:{ticket_id}" in overrides:
                    return overrides[f"system-move:{ticket_id}"]
                for index, ticket in enumerate(board):
                    if ticket.ticket_id == ticket_id:
                        if ticket.waiting_for != to_state:
                            return UNEXPECTED_HOOK_CALL
                        board[index] = ticket._replace(state=to_state, waiting_for=None)
                        return HookResult(0, f"{ticket_id}\n", "")
                return UNEXPECTED_HOOK_CALL
            return UNEXPECTED_HOOK_CALL

        result = runner.invoke(
            cli,
            ["pull"],
            env=env,
            obj={"run_hook": _fake_run_hook},
        )
        return PullRun(
            result=result,
            called_hooks=tuple(called_hooks),
            tickets=tuple(board),
        )

    return _run


class PullSweepCase(NamedTuple):
    case_name: str
    tickets: tuple[FakeTicket, ...]
    expected_output: str
    expected_tickets: tuple[FakeTicket, ...]
    expected_system_move_calls: int


def _pull_sweep_case_id(case: PullSweepCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullSweepCase(
            case_name="nothing_waiting",
            tickets=(
                FakeTicket("ticket-1", "Backlog", "a0", None),
                FakeTicket("ticket-2", "In Progress", "a0", None),
            ),
            expected_output="",
            expected_tickets=(
                FakeTicket("ticket-1", "Backlog", "a0", None),
                FakeTicket("ticket-2", "In Progress", "a0", None),
            ),
            expected_system_move_calls=0,
        ),
        PullSweepCase(
            case_name="one_waiting_ticket",
            tickets=(
                FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),
                FakeTicket("ticket-2", "In Progress", "a0", None),
            ),
            expected_output="ticket-1\n",
            expected_tickets=(
                FakeTicket("ticket-1", "In Progress", "a0", None),
                FakeTicket("ticket-2", "In Progress", "a0", None),
            ),
            expected_system_move_calls=1,
        ),
        PullSweepCase(
            case_name="fills_open_slots_until_limit",
            tickets=(
                FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),
                FakeTicket("ticket-2", "Backlog", "a1", "In Progress"),
                FakeTicket("ticket-3", "Backlog", "a2", "In Progress"),
                FakeTicket("ticket-4", "Backlog", "a3", "In Progress"),
            ),
            expected_output="ticket-1\nticket-2\nticket-3\n",
            expected_tickets=(
                FakeTicket("ticket-1", "In Progress", "a0", None),
                FakeTicket("ticket-2", "In Progress", "a1", None),
                FakeTicket("ticket-3", "In Progress", "a2", None),
                FakeTicket("ticket-4", "Backlog", "a3", "In Progress"),
            ),
            expected_system_move_calls=3,
        ),
        PullSweepCase(
            case_name="priority_order_from_list_waiting",
            tickets=(
                FakeTicket("ticket-1", "In Work", "a0", None),
                FakeTicket("ticket-9", "Backlog", "a0", "In Work"),
                FakeTicket("ticket-3", "Backlog", "a1", "In Work"),
                FakeTicket("ticket-5", "Backlog", "a2", "In Work"),
            ),
            expected_output="ticket-9\nticket-3\n",
            expected_tickets=(
                FakeTicket("ticket-1", "In Work", "a0", None),
                FakeTicket("ticket-9", "In Work", "a0", None),
                FakeTicket("ticket-3", "In Work", "a1", None),
                FakeTicket("ticket-5", "Backlog", "a2", "In Work"),
            ),
            expected_system_move_calls=2,
        ),
        PullSweepCase(
            case_name="chain_opens_upstream_slot",
            tickets=(
                FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),
                FakeTicket("ticket-2", "In Progress", "a0", "In Work"),
                FakeTicket("ticket-3", "In Progress", "a1", None),
                FakeTicket("ticket-4", "In Progress", "a2", None),
            ),
            expected_output="ticket-2\nticket-1\n",
            expected_tickets=(
                FakeTicket("ticket-1", "In Progress", "a0", None),
                FakeTicket("ticket-2", "In Work", "a0", None),
                FakeTicket("ticket-3", "In Progress", "a1", None),
                FakeTicket("ticket-4", "In Progress", "a2", None),
            ),
            expected_system_move_calls=2,
        ),
    ],
    ids=_pull_sweep_case_id,
)
def test_pull_sweep(run_pull: RunPull, case: PullSweepCase) -> None:
    # GIVEN
    expected: PullOutcome = {"exit_code": 0, "output": case.expected_output}
    # WHEN
    run = run_pull(pull_env(), case.tickets, {})
    result = run.result
    # THEN
    assert result.exception is None
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert run.tickets == case.expected_tickets
    assert run.called_hooks.count("fake-system-move") == (
        case.expected_system_move_calls
    )
    assert run.called_hooks.count("fake-describe") == 1


def test_pull_failure_mid_sweep_leaves_earlier_moves_standing(
    run_pull: RunPull,
) -> None:
    # GIVEN
    tickets = (
        FakeTicket("ticket-1", "In Work", "a0", "Done"),
        FakeTicket("ticket-2", "In Progress", "a0", "In Work"),
        FakeTicket("ticket-3", "Backlog", "a0", "In Progress"),
    )
    expected: PullOutcome = {"exit_code": 3, "output": "ticket-1\n"}
    expected_tickets = (
        FakeTicket("ticket-1", "Done", "a0", None),
        FakeTicket("ticket-2", "In Progress", "a0", "In Work"),
        FakeTicket("ticket-3", "Backlog", "a0", "In Progress"),
    )
    # WHEN
    run = run_pull(
        pull_env(),
        tickets,
        {"system-move:ticket-2": HookResult(3, "", "")},
    )
    result = run.result
    # THEN
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert run.tickets == expected_tickets
    assert run.called_hooks.count("fake-system-move") == 2


class PullHookFailureMidSweepCase(NamedTuple):
    case_name: str
    overrides: dict[str, HookResult]
    expected_exit_code: int
    expected_output: str


def _pull_hook_failure_mid_sweep_case_id(
    case: PullHookFailureMidSweepCase,
) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullHookFailureMidSweepCase(
            case_name="count_fails_mid_sweep",
            overrides={"count:In Work": HookResult(3, "", "")},
            expected_exit_code=3,
            expected_output="ticket-1\n",
        ),
        PullHookFailureMidSweepCase(
            case_name="list_waiting_fails_mid_sweep",
            overrides={"list-waiting:In Work": HookResult(3, "", "")},
            expected_exit_code=3,
            expected_output="ticket-1\n",
        ),
    ],
    ids=_pull_hook_failure_mid_sweep_case_id,
)
def test_pull_hook_failure_mid_sweep_leaves_earlier_moves_standing(
    run_pull: RunPull, case: PullHookFailureMidSweepCase
) -> None:
    # GIVEN
    tickets = (
        FakeTicket("ticket-1", "In Work", "a0", "Done"),
        FakeTicket("ticket-2", "In Progress", "a0", "In Work"),
        FakeTicket("ticket-3", "Backlog", "a0", "In Progress"),
    )
    expected: PullOutcome = {
        "exit_code": case.expected_exit_code,
        "output": case.expected_output,
    }
    expected_tickets = (
        FakeTicket("ticket-1", "Done", "a0", None),
        FakeTicket("ticket-2", "In Progress", "a0", "In Work"),
        FakeTicket("ticket-3", "Backlog", "a0", "In Progress"),
    )
    # WHEN
    run = run_pull(pull_env(), tickets, case.overrides)
    result = run.result
    # THEN
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert run.tickets == expected_tickets
    assert run.called_hooks.count("fake-system-move") == 1


def test_pull_without_list_waiting_hook_moves_nothing(run_pull: RunPull) -> None:
    # GIVEN
    tickets = (FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),)
    expected: PullOutcome = {"exit_code": 0, "output": ""}
    # WHEN
    env = pull_env()
    env.pop("LIST_WAITING_HOOK", None)
    run = run_pull(env, tickets, {})
    result = run.result
    # THEN
    assert result.exception is None
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert run.tickets == tickets
    assert "fake-count" not in run.called_hooks
    assert "fake-system-move" not in run.called_hooks


class PullFailureCase(NamedTuple):
    case_name: str
    unset_hooks: tuple[str, ...]
    overrides: dict[str, HookResult]
    expected_exit_code: int
    expected_output: str


def _pull_failure_case_id(case: PullFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PullFailureCase(
            case_name="missing_describe_hook",
            unset_hooks=("DESCRIBE_HOOK",),
            overrides={},
            expected_exit_code=2,
            expected_output="DESCRIBE_HOOK is not set\n",
        ),
        PullFailureCase(
            case_name="failing_describe_hook",
            unset_hooks=(),
            overrides={"describe": HookResult(3, "", "")},
            expected_exit_code=3,
            expected_output="",
        ),
        PullFailureCase(
            case_name="invalid_describe_toml",
            unset_hooks=(),
            overrides={"describe": HookResult(0, "wait = \n", "")},
            expected_exit_code=2,
            expected_output="describe hook output is not valid TOML: Invalid value (at line 1, column 8)\n",
        ),
        PullFailureCase(
            case_name="missing_count_hook",
            unset_hooks=("COUNT_HOOK",),
            overrides={},
            expected_exit_code=2,
            expected_output="COUNT_HOOK is not set\n",
        ),
        PullFailureCase(
            case_name="missing_system_move_hook",
            unset_hooks=("SYSTEM_MOVE_HOOK",),
            overrides={},
            expected_exit_code=2,
            expected_output="SYSTEM_MOVE_HOOK is not set\n",
        ),
        PullFailureCase(
            case_name="system_move_empty_ticket_id",
            unset_hooks=(),
            overrides={"system-move:ticket-1": HookResult(0, "", "")},
            expected_exit_code=2,
            expected_output="system move hook returned no ticket id\n",
        ),
        PullFailureCase(
            case_name="list_waiting_wrong_shape",
            unset_hooks=(),
            overrides={
                "list-waiting:Done": HookResult(0, 'tickets = "ticket-1"\n', "")
            },
            expected_exit_code=2,
            expected_output="invalid list-waiting output: expected tickets\n",
        ),
    ],
    ids=_pull_failure_case_id,
)
def test_pull_hook_failure(run_pull: RunPull, case: PullFailureCase) -> None:
    # GIVEN
    tickets = (FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),)
    expected: PullOutcome = {
        "exit_code": case.expected_exit_code,
        "output": case.expected_output,
    }
    # WHEN
    env = pull_env()
    for hook in case.unset_hooks:
        env.pop(hook, None)
    run = run_pull(env, tickets, case.overrides)
    result = run.result
    # THEN
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert run.tickets == tickets


_PULL_BACKEND_SCRIPT = r"""import json
import os
import sys
from pathlib import Path

STATE_PATH = Path("pull_backend_state.json")
DESCRIBE_VIEW = __DESCRIBE_VIEW__


def load_state():
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    STATE_PATH.write_text(json.dumps(state))


def check_env(expected):
    if {key for key in os.environ if key.startswith("WORKPULL_")} != expected:
        sys.exit(1)


def main():
    hook = sys.argv[1]
    state = load_state()
    if hook == "describe":
        check_env(set())
        sys.stdout.write(DESCRIBE_VIEW)
    elif hook == "count":
        check_env({"WORKPULL_STATE"})
        state_name = os.environ["WORKPULL_STATE"]
        work = sum(
            1 for ticket in state["tickets"] if ticket["state"] == state_name
        )
        wait = sum(
            1
            for ticket in state["tickets"]
            if ticket["waiting_for"] == state_name
        )
        sys.stdout.write(f"wait = {wait}\nwork = {work}\n")
    elif hook == "list-waiting":
        check_env({"WORKPULL_STATE"})
        state_name = os.environ["WORKPULL_STATE"]
        waiting = [
            ticket
            for ticket in state["tickets"]
            if ticket["waiting_for"] == state_name
        ]
        waiting.sort(key=lambda ticket: ticket["priority"])
        names = ", ".join('"' + ticket["ticket"] + '"' for ticket in waiting)
        sys.stdout.write("tickets = [" + names + "]\n")
    elif hook == "system-move":
        check_env({"WORKPULL_TICKET", "WORKPULL_TO_STATE"})
        ticket_id = os.environ["WORKPULL_TICKET"]
        to_state = os.environ["WORKPULL_TO_STATE"]
        for ticket in state["tickets"]:
            if ticket["ticket"] == ticket_id:
                if ticket["waiting_for"] != to_state:
                    sys.exit(1)
                ticket["state"] = to_state
                ticket["waiting_for"] = None
                save_state(state)
                sys.stdout.write(ticket_id + "\n")
                return
        sys.exit(1)
    else:
        sys.exit(1)


main()
"""


def write_pull_backend(
    hook_command: HookCommand, tickets: tuple[FakeTicket, ...]
) -> dict[str, str]:
    """Write the real-hook backend script and its initial state file."""
    Path("mock_pull_backend.py").write_text(
        _PULL_BACKEND_SCRIPT.replace("__DESCRIBE_VIEW__", repr(DESCRIBE_VIEW))
    )
    Path("pull_backend_state.json").write_text(
        json.dumps(
            {
                "tickets": [
                    {
                        "ticket": ticket.ticket_id,
                        "state": ticket.state,
                        "priority": ticket.priority,
                        "waiting_for": ticket.waiting_for,
                    }
                    for ticket in tickets
                ]
            }
        )
    )
    return {
        "DESCRIBE_HOOK": hook_command("mock_pull_backend.py describe"),
        "COUNT_HOOK": hook_command("mock_pull_backend.py count"),
        "LIST_WAITING_HOOK": hook_command("mock_pull_backend.py list-waiting"),
        "SYSTEM_MOVE_HOOK": hook_command("mock_pull_backend.py system-move"),
    }


def read_pull_backend_state() -> tuple[FakeTicket, ...]:
    state = json.loads(Path("pull_backend_state.json").read_text())
    return tuple(
        FakeTicket(
            ticket_id=ticket["ticket"],
            state=ticket["state"],
            priority=ticket["priority"],
            waiting_for=ticket["waiting_for"],
        )
        for ticket in state["tickets"]
    )


def test_pull_real_hook(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    tickets = (
        FakeTicket("ticket-1", "Backlog", "a0", "In Progress"),
        FakeTicket("ticket-2", "In Progress", "a0", None),
    )
    expected: PullOutcome = {"exit_code": 0, "output": "ticket-1\n"}
    expected_tickets = (
        FakeTicket("ticket-1", "In Progress", "a0", None),
        FakeTicket("ticket-2", "In Progress", "a0", None),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_pull_backend(hook_command, tickets)
        env = dict(os.environ)
        env.update(hooks)
        result = runner.invoke(cli, ["pull"], env=env, obj={})
        final_tickets = read_pull_backend_state()
    # THEN
    assert result.exception is None
    actual: PullOutcome = pull_outcome(result)
    assert expected == actual
    assert final_tickets == expected_tickets


def test_pull_help(runner: CliRunner, normalize_help: NormalizeHelp) -> None:
    # GIVEN
    expected: HelpOutcome = {
        "exit_code": 0,
        "help_text": normalize_help("""Usage: cli pull [OPTIONS]

            Pull waiting tickets into open slots.

            Options:
              --help  Show this message and exit.
            """),
    }
    # WHEN
    result = runner.invoke(cli, ["pull", "--help"])
    # THEN
    actual: HelpOutcome = {
        "exit_code": result.exit_code,
        "help_text": normalize_help(result.output),
    }
    assert expected == actual
