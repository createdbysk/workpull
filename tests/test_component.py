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
    unadopted: tuple[str, ...]


class MockBackendHooks(NamedTuple):
    describe: str
    count: str
    get_state: str
    claim_ticket: str
    transition: str
    system_move: str
    list_waiting: str
    release: str
    discard: str
    adopt: str
    prioritize: str


class ComponentTransitionCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    expected_count_output: str
    expected_final_state: MockBackendState


class ComponentPullCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    list_waiting_hook_set: bool
    expected_ticket_3_state_output: str
    expected_opened_count_output: str
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

_MOCK_BACKEND_SCRIPT = r"""import json
import os
import sys
import tomllib
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


def priority_key(number):
    digits = str(number)
    return chr(ord("a") + len(digits) - 1) + digits


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
            if ticket["state"] == state_name
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
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None or ticket["waiting_for"] != os.environ["WORKPULL_TO_STATE"]:
            sys.exit(1)
        ticket["state"] = os.environ["WORKPULL_TO_STATE"]
        ticket["waiting_for"] = None
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    elif hook == "release":
        check_env({"WORKPULL_TICKET", "WORKPULL_TOKEN"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None or ticket["token"] != os.environ["WORKPULL_TOKEN"]:
            sys.exit(1)
        ticket["token"] = None
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    elif hook == "discard":
        check_env({"WORKPULL_TICKET", "WORKPULL_TOKEN"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None or ticket["token"] != os.environ["WORKPULL_TOKEN"]:
            sys.exit(1)
        state["tickets"].remove(ticket)
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    elif hook == "adopt":
        check_env({"WORKPULL_TICKET"})
        ticket_id = os.environ["WORKPULL_TICKET"]
        if ticket_id not in state["unadopted"]:
            sys.exit(1)
        state["unadopted"].remove(ticket_id)
        first_state = tomllib.loads(DESCRIBE_VIEW)["states"][0]
        priority = priority_key(state["next_adopt_key"])
        state["next_adopt_key"] += 1
        state["tickets"].append(
            {
                "ticket": ticket_id,
                "state": first_state,
                "priority": priority,
                "token": None,
                "waiting_for": None,
            }
        )
        save_state(state)
        sys.stdout.write(ticket_id + "\n")
    elif hook == "prioritize":
        check_env({"WORKPULL_TICKET", "WORKPULL_AFTER"})
        ticket = find_ticket(state, os.environ["WORKPULL_TICKET"])
        if ticket is None:
            sys.exit(1)
        after = os.environ["WORKPULL_AFTER"]
        ordered = sorted(
            (item for item in state["tickets"] if item is not ticket),
            key=lambda item: item["priority"],
        )
        if after == "WORKPULL_TOP":
            ordered.insert(0, ticket)
        else:
            anchor = find_ticket(state, after)
            if anchor is None or anchor is ticket:
                sys.exit(1)
            position = next(
                index for index, item in enumerate(ordered) if item is anchor
            )
            ordered.insert(position + 1, ticket)
        for index, item in enumerate(ordered):
            item["priority"] = priority_key(index)
        save_state(state)
        sys.stdout.write(ticket["ticket"] + "\n")
    else:
        sys.exit(1)


main()
"""


def write_mock_backend_with_describe(
    hook_command: HookCommand, initial_state: MockBackendState, describe_view: str
) -> MockBackendHooks:
    """Write the mock backend script and its initial state file.

    The script and state live in the isolated filesystem, so
    the mock backend is test support, not a real backend.
    The describe view is passed explicitly: the cascade
    tests need the chained view, the other tests need
    the default view.
    """
    Path("mock_backend.py").write_text(
        _MOCK_BACKEND_SCRIPT.replace("__DESCRIBE_VIEW__", repr(describe_view))
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
                ],
                "unadopted": list(initial_state.unadopted),
                "next_adopt_key": _initial_next_adopt_key(initial_state),
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
        list_waiting=hook_command("mock_backend.py list-waiting"),
        release=hook_command("mock_backend.py release"),
        discard=hook_command("mock_backend.py discard"),
        adopt=hook_command("mock_backend.py adopt"),
        prioritize=hook_command("mock_backend.py prioritize"),
    )


def _initial_next_adopt_key(initial_state: MockBackendState) -> int:
    """The adopt key counter starts after every key already issued.

    The counter lives in the state file, not in the named
    state, because it is backend bookkeeping: an adopted
    ticket's key must come after every key ever issued,
    even a key whose ticket was later discarded.
    """
    suffixes = [
        int(ticket.priority[1:])
        for ticket in initial_state.tickets
        if ticket.priority[1:].isdigit()
    ]
    return max(suffixes, default=-1) + 1


def write_mock_backend(
    hook_command: HookCommand, initial_state: MockBackendState
) -> MockBackendHooks:
    """Write the mock backend script with the default describe view."""
    return write_mock_backend_with_describe(hook_command, initial_state, DESCRIBE_VIEW)


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
            initial_state=MockBackendState(tickets=(), unadopted=()),
        ),
        MockBackendEnvRejectionCase(
            case_name="count",
            hook_name="count",
            env_vars={"WORKPULL_STATE": "Backlog", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(tickets=(), unadopted=()),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="list_waiting",
            hook_name="list-waiting",
            env_vars={"WORKPULL_STATE": "In Progress", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="release",
            hook_name="release",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
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
                ),
                unadopted=(),
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="discard",
            hook_name="discard",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
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
                ),
                unadopted=(),
            ),
        ),
        MockBackendEnvRejectionCase(
            case_name="adopt",
            hook_name="adopt",
            env_vars={"WORKPULL_TICKET": "ticket-9", "WORKPULL_EXTRA": "1"},
            initial_state=MockBackendState(tickets=(), unadopted=("ticket-9",)),
        ),
        MockBackendEnvRejectionCase(
            case_name="prioritize",
            hook_name="prioritize",
            env_vars={
                "WORKPULL_TICKET": "ticket-1",
                "WORKPULL_AFTER": "ticket-2",
                "WORKPULL_EXTRA": "1",
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
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
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
            key: value
            for key, value in os.environ.items()
            if not key.startswith("WORKPULL_")
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
            initial_state=MockBackendState(tickets=(), unadopted=()),
        ),
        MockBackendErrorCase(
            case_name="claim_ticket_no_unclaimed_ticket",
            hook_name="claim-ticket",
            env_vars={"WORKPULL_STATE": "Backlog"},
            initial_state=MockBackendState(tickets=(), unadopted=()),
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
                ),
                unadopted=(),
            ),
        ),
        MockBackendErrorCase(
            case_name="unknown_hook_name",
            hook_name="bogus",
            env_vars={},
            initial_state=MockBackendState(tickets=(), unadopted=()),
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
            key: value
            for key, value in os.environ.items()
            if not key.startswith("WORKPULL_")
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
        ),
        unadopted=tuple(raw["unadopted"]),
    )


def test_component_describe_prints_mock_backend_view(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    initial_state = MockBackendState(tickets=(), unadopted=())
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hooks.describe
        result = runner.invoke(cli, ["describe"], env=env, obj={})
    # THEN
    assert result.exception is None
    assert result.output.strip() == (
        'states = ["Backlog", "In Progress", "In Work", "Done"]\n'
        "\n"
        "[transitions]\n"
        '"Backlog" = "In Progress"\n'
        '"In Progress" = "Done"\n'
        "\n"
        "[wip_limits]\n"
        '"Backlog" = {work = inf, wait = 3}\n'
        '"In Progress" = {work = 3, wait = 2}\n'
        '"In Work" = {work = 3, wait = 2}\n'
        '"Done" = {work = inf, wait = inf}'
    )


def test_component_count_of_waiting_ticket_counts_work_in_left_state(
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
            MockBackendTicket(
                ticket_id="ticket-2",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["COUNT_HOOK"] = hooks.count
        left_count = runner.invoke(cli, ["count", "Backlog"], env=env, obj={})
        target_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
    # THEN
    assert left_count.exception is None
    assert left_count.output.strip() == "wait = 0\nwork = 1"
    assert target_count.exception is None
    assert target_count.output.strip() == "wait = 1\nwork = 1"


def test_component_transition_pull_after_event_9(
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
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for="Backlog",
            ),
        ),
        unadopted=(),
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
        env["LIST_WAITING_HOOK"] = hooks.list_waiting
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        transition = runner.invoke(
            cli,
            ["transition", "ticket-1", "In Progress", "token-ticket-1"],
            env=env,
            obj={},
        )
        waiting_state = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
        pulled_state = runner.invoke(cli, ["get-state", "ticket-5"], env=env, obj={})
        target_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        opened_count = runner.invoke(cli, ["count", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert transition.exception is None
    assert transition.output.strip() == "ticket-1"
    assert waiting_state.exception is None
    assert waiting_state.output.strip() == "In Progress"
    assert pulled_state.exception is None
    assert pulled_state.output.strip() == "Backlog"
    assert target_count.exception is None
    assert target_count.output.strip() == "wait = 1\nwork = 3"
    assert opened_count.exception is None
    assert opened_count.output.strip() == "wait = 0\nwork = 2"
    assert state == MockBackendState(
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
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
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
        ),
        unadopted=(),
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
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
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
        ),
        unadopted=(),
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
        ),
        unadopted=(),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
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
                ),
                unadopted=(),
            ),
        ),
        ComponentTransitionCase(
            case_name="no_capacity_waiting_ticket_counts_as_work",
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
                        waiting_for="Done",
                    ),
                ),
                unadopted=(),
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
                        waiting_for="Done",
                    ),
                ),
                unadopted=(),
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
            cli,
            ["transition", "ticket-1", "In Progress", "token-ticket-1"],
            env=env,
            obj={},
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


def _component_pull_case_id(case: ComponentPullCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ComponentPullCase(
            case_name="pulls_one_waiting_ticket",
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
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-4",
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
            list_waiting_hook_set=True,
            expected_ticket_3_state_output="In Progress",
            expected_opened_count_output="wait = 1\nwork = 1",
            expected_final_state=MockBackendState(
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
                        state="Done",
                        priority="a0",
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
                    MockBackendTicket(
                        ticket_id="ticket-4",
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
        ),
        ComponentPullCase(
            case_name="without_list_waiting_hook_skips_pull",
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
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
            list_waiting_hook_set=False,
            expected_ticket_3_state_output="In Progress",
            expected_opened_count_output="wait = 1\nwork = 0",
            expected_final_state=MockBackendState(
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
                        state="Done",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
        ),
    ],
    ids=_component_pull_case_id,
)
def test_component_transition_pull(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: ComponentPullCase,
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
        if case.list_waiting_hook_set:
            env["LIST_WAITING_HOOK"] = hooks.list_waiting
        else:
            env.pop("LIST_WAITING_HOOK", None)
        claim = runner.invoke(cli, ["claim-ticket", "In Progress"], env=env, obj={})
        transition = runner.invoke(
            cli, ["transition", "ticket-2", "Done", "token-ticket-2"], env=env, obj={}
        )
        pulled_state = runner.invoke(cli, ["get-state", "ticket-3"], env=env, obj={})
        moved_state = runner.invoke(cli, ["get-state", "ticket-2"], env=env, obj={})
        opened_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        done_count = runner.invoke(cli, ["count", "Done"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    assert transition.exception is None
    assert transition.output.strip() == "ticket-2"
    assert pulled_state.exception is None
    assert pulled_state.output.strip() == case.expected_ticket_3_state_output
    assert moved_state.exception is None
    assert moved_state.output.strip() == "Done"
    assert opened_count.exception is None
    assert opened_count.output.strip() == case.expected_opened_count_output
    assert done_count.exception is None
    assert done_count.output.strip() == "wait = 0\nwork = 1"
    assert state == case.expected_final_state


def test_component_transition_three_step_cascade_pulls_backwards(
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
                state="In Work",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for="In Work",
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for="In Progress",
            ),
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a1",
                token=None,
                waiting_for="Backlog",
            ),
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend_with_describe(
            hook_command, initial_state, CHAINED_DESCRIBE_VIEW
        )
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hooks.describe
        env["COUNT_HOOK"] = hooks.count
        env["GET_STATE_HOOK"] = hooks.get_state
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["TRANSITION_HOOK"] = hooks.transition
        env["SYSTEM_MOVE_HOOK"] = hooks.system_move
        env["LIST_WAITING_HOOK"] = hooks.list_waiting
        claim = runner.invoke(cli, ["claim-ticket", "In Work"], env=env, obj={})
        transition = runner.invoke(
            cli, ["transition", "ticket-2", "Done", "token-ticket-2"], env=env, obj={}
        )
        first_pulled_state = runner.invoke(
            cli, ["get-state", "ticket-3"], env=env, obj={}
        )
        second_pulled_state = runner.invoke(
            cli, ["get-state", "ticket-4"], env=env, obj={}
        )
        moved_state = runner.invoke(cli, ["get-state", "ticket-2"], env=env, obj={})
        in_work_count = runner.invoke(cli, ["count", "In Work"], env=env, obj={})
        in_progress_count = runner.invoke(
            cli, ["count", "In Progress"], env=env, obj={}
        )
        done_count = runner.invoke(cli, ["count", "Done"], env=env, obj={})
        backlog_count = runner.invoke(cli, ["count", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    assert transition.exception is None
    assert transition.output.strip() == "ticket-2"
    assert first_pulled_state.exception is None
    assert first_pulled_state.output.strip() == "In Work"
    assert second_pulled_state.exception is None
    assert second_pulled_state.output.strip() == "In Progress"
    assert moved_state.exception is None
    assert moved_state.output.strip() == "Done"
    assert in_work_count.exception is None
    assert in_work_count.output.strip() == "wait = 0\nwork = 1"
    assert in_progress_count.exception is None
    assert in_progress_count.output.strip() == "wait = 0\nwork = 1"
    assert done_count.exception is None
    assert done_count.output.strip() == "wait = 0\nwork = 1"
    assert backlog_count.exception is None
    assert backlog_count.output.strip() == "wait = 0\nwork = 2"
    assert state == MockBackendState(
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
                state="Done",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Work",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a1",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_transition_cascade_second_pull_at_limit_leaves_first_pull_applied(
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
                state="In Work",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for="In Work",
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for="In Progress",
            ),
            MockBackendTicket(
                ticket_id="ticket-6",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-7",
                state="In Progress",
                priority="a1",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-8",
                state="In Progress",
                priority="a2",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend_with_describe(
            hook_command, initial_state, CHAINED_DESCRIBE_VIEW
        )
        env = dict(os.environ)
        env["DESCRIBE_HOOK"] = hooks.describe
        env["COUNT_HOOK"] = hooks.count
        env["GET_STATE_HOOK"] = hooks.get_state
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["TRANSITION_HOOK"] = hooks.transition
        env["SYSTEM_MOVE_HOOK"] = hooks.system_move
        env["LIST_WAITING_HOOK"] = hooks.list_waiting
        claim = runner.invoke(cli, ["claim-ticket", "In Work"], env=env, obj={})
        transition = runner.invoke(
            cli, ["transition", "ticket-2", "Done", "token-ticket-2"], env=env, obj={}
        )
        first_pulled_state = runner.invoke(
            cli, ["get-state", "ticket-3"], env=env, obj={}
        )
        second_pulled_state = runner.invoke(
            cli, ["get-state", "ticket-4"], env=env, obj={}
        )
        moved_state = runner.invoke(cli, ["get-state", "ticket-2"], env=env, obj={})
        in_work_count = runner.invoke(cli, ["count", "In Work"], env=env, obj={})
        in_progress_count = runner.invoke(
            cli, ["count", "In Progress"], env=env, obj={}
        )
        done_count = runner.invoke(cli, ["count", "Done"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    assert transition.exception is None
    assert transition.output.strip() == "ticket-2"
    assert first_pulled_state.exception is None
    assert first_pulled_state.output.strip() == "In Work"
    assert second_pulled_state.exception is None
    assert second_pulled_state.output.strip() == "In Progress"
    assert moved_state.exception is None
    assert moved_state.output.strip() == "Done"
    assert in_work_count.exception is None
    assert in_work_count.output.strip() == "wait = 0\nwork = 1"
    assert in_progress_count.exception is None
    assert in_progress_count.output.strip() == "wait = 1\nwork = 3"
    assert done_count.exception is None
    assert done_count.output.strip() == "wait = 0\nwork = 1"
    assert state == MockBackendState(
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
                state="Done",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-3",
                state="In Work",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="Backlog",
                priority="a0",
                token=None,
                waiting_for="In Progress",
            ),
            MockBackendTicket(
                ticket_id="ticket-6",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-7",
                state="In Progress",
                priority="a1",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-8",
                state="In Progress",
                priority="a2",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_discard_removes_claimed_ticket_and_its_wip(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["COUNT_HOOK"] = hooks.count
        env["GET_STATE_HOOK"] = hooks.get_state
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["DISCARD_HOOK"] = hooks.discard
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        discard = runner.invoke(
            cli,
            ["discard", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        discarded_state = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
        backlog_count = runner.invoke(cli, ["count", "Backlog"], env=env, obj={})
        in_progress_count = runner.invoke(
            cli, ["count", "In Progress"], env=env, obj={}
        )
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert discard.exception is None
    assert discard.output.strip() == "ticket-1"
    assert discarded_state.exit_code == 1
    assert discarded_state.output.strip() == ""
    assert backlog_count.exception is None
    assert backlog_count.output.strip() == "wait = 0\nwork = 0"
    assert in_progress_count.exception is None
    assert in_progress_count.output.strip() == "wait = 0\nwork = 2"
    assert state == MockBackendState(
        tickets=(
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
        ),
        unadopted=(),
    )


def test_component_discard_makes_token_invalid(
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
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
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
        env["LIST_WAITING_HOOK"] = hooks.list_waiting
        env["RELEASE_HOOK"] = hooks.release
        env["DISCARD_HOOK"] = hooks.discard
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        discard = runner.invoke(
            cli,
            ["discard", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        release = runner.invoke(
            cli,
            ["release", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        transition = runner.invoke(
            cli,
            ["transition", "ticket-1", "In Progress", "token-ticket-1"],
            env=env,
            obj={},
        )
        second_discard = runner.invoke(
            cli,
            ["discard", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert discard.exception is None
    assert discard.output.strip() == "ticket-1"
    assert release.exit_code == 1
    assert release.output.strip() == ""
    assert transition.exit_code == 1
    assert transition.output.strip() == ""
    assert second_discard.exit_code == 1
    assert second_discard.output.strip() == ""
    assert state == MockBackendState(
        tickets=(
            MockBackendTicket(
                ticket_id="ticket-2",
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_discard_with_another_tickets_token_keeps_claim(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["DISCARD_HOOK"] = hooks.discard
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        discard = runner.invoke(
            cli,
            ["discard", "ticket-1", "token-ticket-2"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
    assert discard.exit_code == 1
    assert discard.output.strip() == ""
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
        ),
        unadopted=(),
    )


def test_component_discard_without_claim_fails(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["DISCARD_HOOK"] = hooks.discard
        discard = runner.invoke(
            cli,
            ["discard", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert discard.exit_code == 1
    assert discard.output.strip() == ""
    assert state == initial_state


def test_component_release_ends_claim_and_ticket_can_be_claimed_again(
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
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
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
        env["RELEASE_HOOK"] = hooks.release
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        release = runner.invoke(
            cli,
            ["release", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        stale_transition = runner.invoke(
            cli,
            ["transition", "ticket-1", "In Progress", "token-ticket-1"],
            env=env,
            obj={},
        )
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        ticket_state = runner.invoke(cli, ["get-state", "ticket-1"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert claim.exception is None
    assert claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert release.exception is None
    assert release.output.strip() == "ticket-1"
    assert stale_transition.exit_code == 1
    assert stale_transition.output.strip() == ""
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    )
    assert ticket_state.exception is None
    assert ticket_state.output.strip() == "Backlog"
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
                state="In Progress",
                priority="a0",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_release_with_another_tickets_token_keeps_claim(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["RELEASE_HOOK"] = hooks.release
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        release = runner.invoke(
            cli,
            ["release", "ticket-1", "token-ticket-2"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
    assert release.exit_code == 1
    assert release.output.strip() == ""
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
        ),
        unadopted=(),
    )


def test_component_release_without_claim_fails(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["RELEASE_HOOK"] = hooks.release
        release = runner.invoke(
            cli,
            ["release", "ticket-1", "token-ticket-1"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert release.exit_code == 1
    assert release.output.strip() == ""
    assert state == initial_state


def test_component_adopt_assigns_first_state_and_lowest_priority(
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
        ),
        unadopted=("ticket-3",),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["ADOPT_HOOK"] = hooks.adopt
        adopt = runner.invoke(cli, ["adopt", "ticket-3"], env=env, obj={})
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        third_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert adopt.exception is None
    assert adopt.output.strip() == "ticket-3"
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
    assert third_claim.exception is None
    assert third_claim.output.strip() == 'ticket = "ticket-3"\ntoken = "token-ticket-3"'
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
                state="Backlog",
                priority="a2",
                token="token-ticket-3",
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


class ComponentAdoptRejectionCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    ticket_id: str


def _component_adopt_rejection_case_id(case: ComponentAdoptRejectionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ComponentAdoptRejectionCase(
            case_name="already_adopted",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
        ),
        ComponentAdoptRejectionCase(
            case_name="already_in_progress",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="In Progress",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
        ),
    ],
    ids=_component_adopt_rejection_case_id,
)
def test_component_adopt_rejects_ticket_already_in_system(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: ComponentAdoptRejectionCase,
) -> None:
    # GIVEN
    initial_state = case.initial_state
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["ADOPT_HOOK"] = hooks.adopt
        adopt = runner.invoke(cli, ["adopt", case.ticket_id], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert adopt.exit_code == 1
    assert adopt.output.strip() == ""
    assert state == initial_state


def test_component_adopt_with_many_tickets_claims_adopted_ticket_last(
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
                state="Backlog",
                priority="a2",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="Backlog",
                priority="a3",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a4",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-6",
                state="Backlog",
                priority="a5",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-7",
                state="Backlog",
                priority="a6",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-8",
                state="Backlog",
                priority="a7",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-9",
                state="Backlog",
                priority="a8",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-10",
                state="Backlog",
                priority="a9",
                token=None,
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-11",
                state="Backlog",
                priority="b10",
                token=None,
                waiting_for=None,
            ),
        ),
        unadopted=("ticket-12",),
    )
    expected_claim_order = (
        "ticket-1",
        "ticket-2",
        "ticket-3",
        "ticket-4",
        "ticket-5",
        "ticket-6",
        "ticket-7",
        "ticket-8",
        "ticket-9",
        "ticket-10",
        "ticket-11",
        "ticket-12",
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["ADOPT_HOOK"] = hooks.adopt
        adopt = runner.invoke(cli, ["adopt", "ticket-12"], env=env, obj={})
        claims = [
            runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
            for _ in expected_claim_order
        ]
        state = read_mock_backend_state()
    # THEN
    assert adopt.exception is None
    assert adopt.output.strip() == "ticket-12"
    for claim, ticket_id in zip(claims, expected_claim_order, strict=True):
        assert claim.exception is None
        assert (
            claim.output.strip()
            == f'ticket = "{ticket_id}"\ntoken = "token-{ticket_id}"'
        )
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
                state="Backlog",
                priority="a2",
                token="token-ticket-3",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-4",
                state="Backlog",
                priority="a3",
                token="token-ticket-4",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-5",
                state="Backlog",
                priority="a4",
                token="token-ticket-5",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-6",
                state="Backlog",
                priority="a5",
                token="token-ticket-6",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-7",
                state="Backlog",
                priority="a6",
                token="token-ticket-7",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-8",
                state="Backlog",
                priority="a7",
                token="token-ticket-8",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-9",
                state="Backlog",
                priority="a8",
                token="token-ticket-9",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-10",
                state="Backlog",
                priority="a9",
                token="token-ticket-10",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-11",
                state="Backlog",
                priority="b10",
                token="token-ticket-11",
                waiting_for=None,
            ),
            MockBackendTicket(
                ticket_id="ticket-12",
                state="Backlog",
                priority="b11",
                token="token-ticket-12",
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_adopt_two_tickets_keys_increase_in_adoption_order(
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
        ),
        unadopted=("ticket-2", "ticket-3"),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["ADOPT_HOOK"] = hooks.adopt
        first_adopt = runner.invoke(cli, ["adopt", "ticket-2"], env=env, obj={})
        second_adopt = runner.invoke(cli, ["adopt", "ticket-3"], env=env, obj={})
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        third_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert first_adopt.exception is None
    assert first_adopt.output.strip() == "ticket-2"
    assert second_adopt.exception is None
    assert second_adopt.output.strip() == "ticket-3"
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
    assert third_claim.exception is None
    assert third_claim.output.strip() == 'ticket = "ticket-3"\ntoken = "token-ticket-3"'
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
                state="Backlog",
                priority="a2",
                token="token-ticket-3",
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


def test_component_adopt_after_discard_of_highest_key_comes_after_every_issued_key(
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
        ),
        unadopted=("ticket-3",),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["DISCARD_HOOK"] = hooks.discard
        env["ADOPT_HOOK"] = hooks.adopt
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        discard = runner.invoke(
            cli,
            ["discard", "ticket-2", "token-ticket-2"],
            env=env,
            obj={},
        )
        adopt = runner.invoke(cli, ["adopt", "ticket-3"], env=env, obj={})
        third_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert first_claim.exception is None
    assert first_claim.output.strip() == 'ticket = "ticket-1"\ntoken = "token-ticket-1"'
    assert second_claim.exception is None
    assert (
        second_claim.output.strip() == 'ticket = "ticket-2"\ntoken = "token-ticket-2"'
    )
    assert discard.exception is None
    assert discard.output.strip() == "ticket-2"
    assert adopt.exception is None
    assert adopt.output.strip() == "ticket-3"
    assert third_claim.exception is None
    assert third_claim.output.strip() == 'ticket = "ticket-3"\ntoken = "token-ticket-3"'
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
                ticket_id="ticket-3",
                state="Backlog",
                priority="a2",
                token="token-ticket-3",
                waiting_for=None,
            ),
        ),
        unadopted=(),
    )


class ComponentPrioritizeCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    ticket_id: str
    after: str
    expected_claim_output: str
    expected_final_state: MockBackendState


def _component_prioritize_case_id(case: ComponentPrioritizeCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ComponentPrioritizeCase(
            case_name="move_after_last_ticket",
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
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
            after="ticket-3",
            expected_claim_output='ticket = "ticket-2"\ntoken = "token-ticket-2"',
            expected_final_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="Backlog",
                        priority="a0",
                        token="token-ticket-2",
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
        ),
        ComponentPrioritizeCase(
            case_name="move_to_top",
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
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-3",
            after="WORKPULL_TOP",
            expected_claim_output='ticket = "ticket-3"\ntoken = "token-ticket-3"',
            expected_final_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-2",
                        state="Backlog",
                        priority="a2",
                        token=None,
                        waiting_for=None,
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a0",
                        token="token-ticket-3",
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
        ),
    ],
    ids=_component_prioritize_case_id,
)
def test_component_prioritize_reorders_tickets(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: ComponentPrioritizeCase,
) -> None:
    # GIVEN
    initial_state = case.initial_state
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
        env["PRIORITIZE_HOOK"] = hooks.prioritize
        prioritize = runner.invoke(
            cli,
            ["prioritize", case.ticket_id, case.after],
            env=env,
            obj={},
        )
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        state = read_mock_backend_state()
    # THEN
    assert prioritize.exception is None
    assert prioritize.output.strip() == case.ticket_id
    assert claim.exception is None
    assert claim.output.strip() == case.expected_claim_output
    assert state == case.expected_final_state


def test_component_prioritize_with_unknown_after_ticket_fails(
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
        ),
        unadopted=(),
    )
    # WHEN
    with isolated_filesystem():
        hooks = write_mock_backend(hook_command, initial_state)
        env = dict(os.environ)
        env["PRIORITIZE_HOOK"] = hooks.prioritize
        prioritize = runner.invoke(
            cli,
            ["prioritize", "ticket-1", "ticket-9"],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert prioritize.exit_code == 1
    assert prioritize.output.strip() == ""
    assert state == initial_state


class ComponentCanTransitionCase(NamedTuple):
    case_name: str
    initial_state: MockBackendState
    ticket_id: str
    to_state: str
    expected_output: str


def _component_can_transition_case_id(case: ComponentCanTransitionCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        ComponentCanTransitionCase(
            case_name="reachable_with_wait_capacity",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
            to_state="In Progress",
            expected_output="true",
        ),
        ComponentCanTransitionCase(
            case_name="unreachable_from_backlog",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
            to_state="Done",
            expected_output="false",
        ),
        ComponentCanTransitionCase(
            case_name="unknown_to_state",
            initial_state=MockBackendState(
                tickets=(
                    MockBackendTicket(
                        ticket_id="ticket-1",
                        state="Backlog",
                        priority="a0",
                        token=None,
                        waiting_for=None,
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
            to_state="Nowhere",
            expected_output="false",
        ),
        ComponentCanTransitionCase(
            case_name="wait_limit_reached",
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
                        state="Backlog",
                        priority="a1",
                        token=None,
                        waiting_for="In Progress",
                    ),
                    MockBackendTicket(
                        ticket_id="ticket-3",
                        state="Backlog",
                        priority="a2",
                        token=None,
                        waiting_for="In Progress",
                    ),
                ),
                unadopted=(),
            ),
            ticket_id="ticket-1",
            to_state="In Progress",
            expected_output="false",
        ),
    ],
    ids=_component_can_transition_case_id,
)
def test_component_can_transition_answers_from_backend_facts(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
    case: ComponentCanTransitionCase,
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
        result = runner.invoke(
            cli,
            ["can-transition", case.ticket_id, case.to_state],
            env=env,
            obj={},
        )
        state = read_mock_backend_state()
    # THEN
    assert result.exception is None
    assert result.output.strip() == case.expected_output
    assert state == initial_state
