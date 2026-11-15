"""Component tests for the live GitHub adapter.

The real CLI runs with the adapter hooks wired in
through the environment, against the file-backed fake
GitHub layer. No live GitHub call is made.
"""

import contextlib
import json
import os
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from click.testing import CliRunner

from workpull.cli import cli

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = ROOT / "plugins" / "github_adapter"

IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]
HookCommand = Callable[[str], str]

CONFIG = (
    'states = ["Backlog", "In Progress", "Done"]\n'
    "\n"
    "[transitions]\n"
    'Backlog = "In Progress"\n'
    '"In Progress" = "Done"\n'
    "\n"
    "[wip_limits]\n"
    "Backlog = {work = inf, wait = inf}\n"
    '"In Progress" = {work = 1, wait = inf}\n'
    "Done = {work = inf, wait = inf}\n"
)


class FakeIssue(NamedTuple):
    number: str
    body: str
    labels: tuple[str, ...]


class AdapterHooks(NamedTuple):
    describe: str
    adopt: str
    prioritize: str
    claim_ticket: str
    release: str
    transition: str
    discard: str
    count: str
    get_state: str
    list_waiting: str
    system_move: str


def write_github_state(issues: list[FakeIssue]) -> None:
    Path("github_state.json").write_text(
        json.dumps(
            {
                "config": CONFIG,
                "issues": [
                    {
                        "number": issue.number,
                        "body": issue.body,
                        "labels": list(issue.labels),
                    }
                    for issue in issues
                ],
            }
        )
    )


def adapter_hooks(hook_command: HookCommand) -> AdapterHooks:
    def hook(script: str) -> str:
        return hook_command((ADAPTER_DIR / script).as_posix())

    return AdapterHooks(
        describe=hook("describe.py"),
        adopt=hook("adopt.py"),
        prioritize=hook("prioritize.py"),
        claim_ticket=hook("claim_ticket.py"),
        release=hook("release.py"),
        transition=hook("transition.py"),
        discard=hook("discard.py"),
        count=hook("count.py"),
        get_state=hook("get_state.py"),
        list_waiting=hook("list_waiting.py"),
        system_move=hook("system_move.py"),
    )


def adapter_env(hooks: AdapterHooks) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("WORKPULL_")
    }
    env["WORKPULL_GITHUB_STATE_FILE"] = "github_state.json"
    env["DESCRIBE_HOOK"] = hooks.describe
    env["ADOPT_HOOK"] = hooks.adopt
    env["PRIORITIZE_HOOK"] = hooks.prioritize
    env["CLAIM_TICKET_HOOK"] = hooks.claim_ticket
    env["RELEASE_HOOK"] = hooks.release
    env["TRANSITION_HOOK"] = hooks.transition
    env["DISCARD_HOOK"] = hooks.discard
    env["COUNT_HOOK"] = hooks.count
    env["GET_STATE_HOOK"] = hooks.get_state
    env["LIST_WAITING_HOOK"] = hooks.list_waiting
    env["SYSTEM_MOVE_HOOK"] = hooks.system_move
    return env


def claim_token(output: str) -> str:
    token = tomllib.loads(output)["token"]
    assert isinstance(token, str)
    return token


def test_component_end_to_end_flow(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    issues = [
        FakeIssue(number="1", body="First issue", labels=()),
        FakeIssue(number="2", body="Second issue", labels=()),
    ]
    # WHEN
    with isolated_filesystem():
        write_github_state(issues)
        env = adapter_env(adapter_hooks(hook_command))
        describe = runner.invoke(cli, ["describe"], env=env, obj={})
        adopt_one = runner.invoke(cli, ["adopt", "1"], env=env, obj={})
        adopt_two = runner.invoke(cli, ["adopt", "2"], env=env, obj={})
        adopt_again = runner.invoke(cli, ["adopt", "1"], env=env, obj={})
        first_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        first_token = claim_token(first_claim.output)
        first_move = runner.invoke(
            cli,
            ["transition", "1", "In Progress", first_token],
            env=env,
            obj={},
        )
        first_state = runner.invoke(cli, ["get-state", "1"], env=env, obj={})
        second_claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        second_token = claim_token(second_claim.output)
        second_move = runner.invoke(
            cli,
            ["transition", "2", "In Progress", second_token],
            env=env,
            obj={},
        )
        waiting_state = runner.invoke(cli, ["get-state", "2"], env=env, obj={})
        full_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        done_claim = runner.invoke(
            cli, ["claim-ticket", "In Progress"], env=env, obj={}
        )
        done_token = claim_token(done_claim.output)
        done_move = runner.invoke(
            cli, ["transition", "1", "Done", done_token], env=env, obj={}
        )
        pulled_state = runner.invoke(cli, ["get-state", "2"], env=env, obj={})
        pulled_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        discard_claim = runner.invoke(
            cli, ["claim-ticket", "In Progress"], env=env, obj={}
        )
        discard_token = claim_token(discard_claim.output)
        discard = runner.invoke(cli, ["discard", "2", discard_token], env=env, obj={})
        empty_count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
        discarded_state = runner.invoke(cli, ["get-state", "2"], env=env, obj={})
    # THEN
    assert describe.exception is None
    assert describe.output.strip() == (
        'states = ["Backlog", "In Progress", "Done"]\n'
        "\n"
        "[transitions]\n"
        '"Backlog" = "In Progress"\n'
        '"In Progress" = "Done"\n'
        "\n"
        "[wip_limits]\n"
        '"Backlog" = {work = inf, wait = inf}\n'
        '"In Progress" = {work = 1, wait = inf}\n'
        '"Done" = {work = inf, wait = inf}'
    )
    assert adopt_one.exception is None
    assert adopt_one.output.strip() == "1"
    assert adopt_two.exception is None
    assert adopt_two.output.strip() == "2"
    assert adopt_again.exit_code == 1
    assert adopt_again.output.strip() == ""
    assert first_claim.exception is None
    assert tomllib.loads(first_claim.output)["ticket"] == "1"
    assert first_move.exception is None
    assert first_move.output.strip() == "1"
    assert first_state.exception is None
    assert first_state.output.strip() == "In Progress"
    assert second_claim.exception is None
    assert tomllib.loads(second_claim.output)["ticket"] == "2"
    assert second_move.exception is None
    assert second_move.output.strip() == "2"
    assert waiting_state.exception is None
    assert waiting_state.output.strip() == "In Progress"
    assert full_count.exception is None
    assert full_count.output.strip() == "wait = 1\nwork = 1"
    assert done_claim.exception is None
    assert tomllib.loads(done_claim.output)["ticket"] == "1"
    assert done_move.exception is None
    assert done_move.output.strip() == "1"
    assert pulled_state.exception is None
    assert pulled_state.output.strip() == "In Progress"
    assert pulled_count.exception is None
    assert pulled_count.output.strip() == "wait = 0\nwork = 1"
    assert discard_claim.exception is None
    assert tomllib.loads(discard_claim.output)["ticket"] == "2"
    assert discard.exception is None
    assert discard.output.strip() == "2"
    assert empty_count.exception is None
    assert empty_count.output.strip() == "wait = 0\nwork = 0"
    assert discarded_state.exit_code == 1
    assert discarded_state.output.strip() == ""


def test_component_prioritize_changes_claim_order(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    issues = [
        FakeIssue(number="1", body="First issue", labels=()),
        FakeIssue(number="2", body="Second issue", labels=()),
    ]
    # WHEN
    with isolated_filesystem():
        write_github_state(issues)
        env = adapter_env(adapter_hooks(hook_command))
        runner.invoke(cli, ["adopt", "1"], env=env, obj={})
        runner.invoke(cli, ["adopt", "2"], env=env, obj={})
        prioritize = runner.invoke(
            cli, ["prioritize", "2", "WORKPULL_TOP"], env=env, obj={}
        )
        claim = runner.invoke(cli, ["claim-ticket", "Backlog"], env=env, obj={})
        token = claim_token(claim.output)
        release = runner.invoke(cli, ["release", "2", token], env=env, obj={})
        wrong_release = runner.invoke(cli, ["release", "2", token], env=env, obj={})
    # THEN
    assert prioritize.exception is None
    assert prioritize.output.strip() == "2"
    assert claim.exception is None
    assert tomllib.loads(claim.output)["ticket"] == "2"
    assert release.exception is None
    assert release.output.strip() == "2"
    assert wrong_release.exit_code == 1
    assert wrong_release.output.strip() == ""


def test_component_pull_moves_waiting_ticket_into_open_slot(
    runner: CliRunner,
    isolated_filesystem: IsolatedFilesystem,
    hook_command: HookCommand,
) -> None:
    # GIVEN
    waiting_body = (
        "Waiting issue\n"
        "\n"
        "<!-- workpull:record:start -->\n"
        "```toml\n"
        'key = "5"\n'
        'waiting_for = "In Progress"\n'
        "```\n"
        "<!-- workpull:record:end -->\n"
    )
    issues = [FakeIssue(number="3", body=waiting_body, labels=("workpull:Backlog",))]
    # WHEN
    with isolated_filesystem():
        write_github_state(issues)
        env = adapter_env(adapter_hooks(hook_command))
        pull = runner.invoke(cli, ["pull"], env=env, obj={})
        state = runner.invoke(cli, ["get-state", "3"], env=env, obj={})
        count = runner.invoke(cli, ["count", "In Progress"], env=env, obj={})
    # THEN
    assert pull.exception is None
    assert pull.output.strip() == "3"
    assert state.exception is None
    assert state.output.strip() == "In Progress"
    assert count.exception is None
    assert count.output.strip() == "wait = 0\nwork = 1"
