"""Component tests for workpull, against a mock backend that holds state."""

import contextlib

import pytest
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from click.testing import CliRunner
from collections.abc import Callable

from workpull.cli import cli

IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]


class MockBackendTicket(NamedTuple):
    ticket_id: str
    state: str
    priority: str
    token: str | None
    waiting_for: str | None


class MockBackendState(NamedTuple):
    tickets: tuple[MockBackendTicket, ...]


class MockBackendHooks(NamedTuple):
    describe: str
    count: str
    get_state: str
    claim_ticket: str
    transition: str
    system_move: str


class ComponentTransitionCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    expected_count_output: str
    expected_final_state: MockBackendState


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

_MOCK_BACKEND_SCRIPT = r"""import json
import os
import sys
from pathlib import Path

STATE_PATH = Path("mock_backend_state.json")
DESCRIBE_VIEW = __DESCRIBE_VIEW__


def load_state():
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    STATE_PATH.write_text(json.dumps(state))


def find_ticket(state, ticket_id):
    for ticket in state["tickets"]:
        if ticket["ticket"] == ticket_id:
            return ticket
    return None


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
            1
            for ticket in state["tickets"]
            if ticket["state"] == state_name and ticket["waiting_for"] is None
        )
        wait = sum(
            1
            for ticket in state["tickets"]
            if ticket["waiting_for"] == state_name
        )
        sys.stdout.write(f"wait = {wait}\nwork = {work}\n")
    elif hook == "get-state":
        check_env({"WORKPULL_TICKET"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None:
            sys.exit(1)
        current_state = ticket["waiting_for"] or ticket["state"]
        sys.stdout.write(current_state + "\n")
    elif hook == "claim-ticket":
        check_env({"WORKPULL_STATE"})
        state_name = os.environ["WORKPULL_STATE"]
        candidates = [
            ticket
            for ticket in state["tickets"]
            if ticket["state"] == state_name
            and ticket["waiting_for"] is None
            and ticket["token"] is None
        ]
        candidates.sort(key=lambda ticket: ticket["priority"])
        if not candidates:
            sys.exit(1)
        ticket = candidates[0]
        ticket["token"] = "token-" + ticket["ticket"]
        save_state(state)
        ticket_id = ticket["ticket"]
        sys.stdout.write('ticket = "' + ticket_id + '"\ntoken = "token-' + ticket_id + '"\n')
    elif hook == "transition":
        check_env({"WORKPULL_TICKET", "WORKPULL_TO_STATE", "WORKPULL_TOKEN"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None or ticket["token"] != os.environ["WORKPULL_TOKEN"]:
            sys.exit(1)
        ticket["waiting_for"] = os.environ["WORKPULL_TO_STATE"]
        ticket["token"] = None
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    elif hook == "system-move":
        check_env({"WORKPULL_TICKET", "WORKPULL_TO_STATE"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None or ticket["waiting_for"] != os.environ["WORKPULL_TO_STATE"]:
            sys.exit(1)
        ticket["state"] = os.environ["WORKPULL_TO_STATE"]
        ticket["waiting_for"] = None
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    else:
        sys.exit(1)


main()
"""


def write_mock_backend(
    hook_command: HookCommand, initial_state: MockBackendState
) -> MockBackendHooks:
    """Write the mock backend script and its initial state file.

    The script and state live in the isolated filesystem, so
    the mock backend is test support, not a real backend.
    """
    Path("mock_backend.py").write_text(
        _MOCK_BACKEND_SCRIPT.replace("__DESCRIBE_VIEW__", repr(DESCRIBE_VIEW))
    )
    Path("mock_backend_state.json").write_text(
        json.dumps(
            {
                "tickets": [
                    {
                        "ticket": ticket.ticket_id,
                        "state": ticket.state,
                        "priority": ticket.priority,
                        "token": ticket.token,
                        "waiting_for": ticket.waiting_for,
                    }
                    for ticket in initial_state.tickets
                ]
            }
        )
    )
    return MockBackendHooks(
        describe=hook_command("mock_backend.py describe"),
        count=hook_command("mock_backend.py count"),
        get_state=hook_command("mock_backend.py get-state"),
        claim_ticket=hook_command("mock_backend.py claim-ticket"),
        transition=hook_command("mock_backend.py transition"),
        system_move=hook_command("mock_backend.py system-move"),
    )



class MockBackendEnvRejectionCase(NamedTuple):
    case_name: str
    hook_name: str
    env_vars: dict[str, str]
    initial_state: MockBackendState


def _mock_backend_env_rejection_case_id(case: MockBackendEnvRejectionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        MockBackendEnvRejectionCase(
            case_name="describe",
            hook_name="describe",
            env_vars={"WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(tickets=()),
        ),
        MockBackendEnvRejectionCase(
            case_name="count",
            hook_name="count",
            env_vars={"WORKPULL_STATE": "Backlog", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(tickets=()),
        ),
        MockBackendEnvRejectionCase(
            case_name="get_state",
            hook_name="get-state",
            env_vars={"WORKPULL_TICKET": "ticket-1", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="claim_ticket",
            hook_name="claim-ticket",
            env_vars={"WORKPULL_STATE": "Backlog", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="transition",
            hook_name="transition",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
                "WORKPULL_TO_STATE": "In Progress",
                "WORKPULL_TOKEN": "token-ticket-1",
                "WORKPULL_EXTRA": "1",
            },
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token="token-ticket-1",
                        waiting_for=None,
                    ),
                )
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="system_move",
            hook_name="system-move",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
                "WORKPULL_TO_STATE": "In Progress",
                "WORKPULL_EXTRA": "1",
            },
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                )
            ),
        ),
    ],
    ids=_mock_backend_env_rejection_case_id,
)
def test_mock_backend_rejects_extra_workpull_env(
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: MockBackendEnvRejectionCase,
) -> None:
    # GIVEN
    initial_state = case.initial_state
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("WORKPULL_")
        }
        env.update(case.env_vars)
        probe = subprocess.run(
            [sys.executable, "mock_backend.py", case.hook_name],
            env=env,
            capture_output=True,
            text=True,
        )
    # THEN
    assert probe.returncode == 1
    assert probe.stdout == ""


class MockBackendErrorCase(NamedTuple):
    case_name: str
    hook_name: str
    env_vars: dict[str, str]
    initial_state: MockBackendState


def _mock_backend_error_case_id(case: MockBackendErrorCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        MockBackendErrorCase(
            case_name="get_state_unknown_ticket",
            hook_name="get-state",
            env_vars={"WORKPULL_TICKET": "ticket-9"},
            initial_state=MockBackendState(tickets=()),
        ),
        MockBackendErrorCase(
            case_name="claim_ticket_no_unclaimed_ticket",
            hook_name="claim-ticket",
            env_vars={"WORKPULL_STATE": "Backlog"},
            initial_state=MockBackendState(tickets=()),
        ),
        MockBackendErrorCase(
            case_name="system_move_ticket_not_waiting_for_to_state",
            hook_name="system-move",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
                "WORKPULL_TO_STATE": "In Progress",
            },
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
        ),
        MockBackendErrorCase(
            case_name="unknown_hook_name",
            hook_name="bogus",
            env_vars={},
            initial_state=MockBackendState(tickets=()),
        ),
    ],
    ids=_mock_backend_error_case_id,
)
def test_mock_backend_error_branches_exit_1(
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: MockBackendErrorCase,
) -> None:
    # GIVEN
    initial_state = case.initial_state
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("WORKPULL_")
        }
        env.update(case.env_vars)
        probe = subprocess.run(
            [sys.executable, "mock_backend.py", case.hook_name],
            env=env,
            capture_output=True,
            text=True,
        )
    # THEN
    assert probe.returncode == 1
    assert probe.stdout == ""


def read_mock_backend_state() -> MockBackendState:
    """Read the mock backend state file back into named types."""
    raw = json.loads(Path("mock_backend_state.json").read_text())
    return MockBackendState(
        tickets=tuple(
            MockBackendTicket(
                ticket_id=ticket["ticket"],
                state=ticket["state"],
                priority=ticket["priority"],
                token=ticket["token"],
                waiting_for=ticket["waiting_for"],
            )
            for ticket in raw["tickets"]
        )
    )



def test_component_transition_with_another_ticket_token_does_not_move(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    initial_state = MockBackendState(
        tickets=(
            MockBackendTicket(
                ticket_id="ticket-1",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-2",
                state="Backlog",
                priority="a1",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        )
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hooks.describe
        env["COUNT_HOOK"] = hooks.count
        env["GET_STATE_HOOK"] = hooks.get_state
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["TRANSITION_HOOK"] = hooks.transition
        env["SYSTEM_MOVE_HOOK"] = hooks.system_move
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        transition = runner.invoke(
            cli,
            ["transition", "ticket-2", "In Progress", "token-ticket-1"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    assert transition.exit_code == 1
    assert transition.output.strip() == ""
    assert state == MockBackendState(
        tickets=(
            MockBackendTicket(
                ticket_id="ticket-1",
                state="Backlog",
                priority="a0",
                token="token-ticket-1",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-2",
                state="Backlog",
                priority="a1",
                token="token-ticket-2",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        )
    )



def test_component_get_state_of_waiting_ticket_returns_waiting_for_state(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    initial_state = MockBackendState(
        tickets=(
            MockBackendTicket(
                ticket_id="ticket-1",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for="In Progress",
            ),
        )
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["GET_STATE_HOOK"] = hooks.get_state
        result = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
    # THEN
    assert result.exception is None
    assert result.output.strip() == "In Progress"



def _component_transition_case_id(case: ComponentTransitionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ComponentTransitionCase(
            case_name="capacity_available",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="In Progress",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
            expected_count_output="wait = 0\nwork = 3",
            expected_final_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="In Progress",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
        ),
        ComponentTransitionCase(
            case_name="no_capacity_at_limit",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="In Progress",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-4",
                        state="In Progress",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
            expected_count_output="wait = 1\nwork = 3",
            expected_final_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="In Progress",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-4",
                        state="In Progress",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                )
            ),
        ),
    ],
    ids=_component_transition_case_id,
)
def test_component_transition_capacity(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: ComponentTransitionCase,
) -> None:
    # GIVEN
    initial_state = case.initial_state
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hooks.describe
        env["COUNT_HOOK"] = hooks.count
        env["GET_STATE_HOOK"] = hooks.get_state
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["TRANSITION_HOOK"] = hooks.transition
        env["SYSTEM_MOVE_HOOK"] = hooks.system_move
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        transition = runner.invoke(
            cli, ["transition", "ticket-1", "In Progress", "token-ticket-1"], env=env, obj={}
        )
        final_state = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
        final_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert transition.exception is None
    assert transition.output.strip() == "ticket-1"
    assert final_state.exception is None
    assert final_state.output.strip() == "In Progress"
    assert final_count.exception is None
    assert final_count.output.strip() == case.expected_count_output
    assert state == case.expected_final_state
