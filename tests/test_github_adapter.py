"""Tests for the live GitHub adapter, against a fake GitHub layer.

No live GitHub call is made: operations run against an
in-memory store, and the hook entry points run against
the file-backed store in an isolated filesystem.
"""

import base64
import contextlib
import email.message
import hashlib
import io
import json
import os
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, override

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = ROOT / "plugins" / "github_adapter"
sys.path.insert(0, str(ROOT))

from plugins.github_adapter import github_backend as backend

IsolatedFilesystem = Callable[[], contextlib.AbstractContextManager[str]]

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


class FakeGithubStore(backend.GithubStore):
    """In-memory GitHub layer: config text plus issues by number."""

    def __init__(self, config: str, issues: list[backend.Issue]) -> None:
        self._config = config
        self._issues = {issue.number: issue for issue in issues}

    @override
    def read_config(self) -> str:
        return self._config

    @override
    def get_issue(self, number: str) -> backend.Issue | None:
        return self._issues.get(number)

    @override
    def list_issues(self) -> list[backend.Issue]:
        return list(self._issues.values())

    @override
    def update_issue(self, issue: backend.Issue) -> None:
        self._issues[issue.number] = issue


def make_store(numbers: list[str]) -> FakeGithubStore:
    return FakeGithubStore(
        CONFIG,
        [
            backend.Issue(number=number, body=f"Body of {number}", labels=())
            for number in numbers
        ],
    )


def record_of(store: FakeGithubStore, number: str) -> backend.Record:
    issue = store.get_issue(number)
    assert issue is not None
    record = backend.parse_record(issue.body)
    assert record is not None
    return record


class KeyBetweenCase(NamedTuple):
    case_name: str
    low_key: str | None
    high_key: str | None
    expected_key: str


def _key_between_case_id(case: KeyBetweenCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        KeyBetweenCase(
            case_name="no_neighbours",
            low_key=None,
            high_key=None,
            expected_key="5",
        ),
        KeyBetweenCase(
            case_name="after_last",
            low_key="5",
            high_key=None,
            expected_key="75",
        ),
        KeyBetweenCase(
            case_name="before_first",
            low_key=None,
            high_key="5",
            expected_key="25",
        ),
        KeyBetweenCase(
            case_name="between_neighbours",
            low_key="5",
            high_key="75",
            expected_key="625",
        ),
        KeyBetweenCase(
            case_name="between_close_neighbours",
            low_key="25",
            high_key="5",
            expected_key="375",
        ),
    ],
    ids=_key_between_case_id,
)
def test_key_between_computes_fractional_midpoint(case: KeyBetweenCase) -> None:
    # GIVEN
    expected = case.expected_key
    # WHEN
    actual = backend.key_between(case.low_key, case.high_key)
    # THEN
    assert actual == expected


def test_describe_prints_repository_config() -> None:
    # GIVEN
    store = make_store([])
    # WHEN
    actual = backend.describe_output(store)
    # THEN
    assert actual == CONFIG


def test_adopt_appends_record_and_first_state_label() -> None:
    # GIVEN
    store = make_store(["1"])
    # WHEN
    adopted = backend.adopt_ticket(store, "1")
    issue = store.get_issue("1")
    # THEN
    assert adopted == "1"
    assert issue is not None
    assert issue.labels == ("workpull:Backlog",)
    assert issue.body == (
        "Body of 1\n"
        "\n"
        "<!-- workpull:record:start -->\n"
        "```toml\n"
        'key = "5"\n'
        "```\n"
        "<!-- workpull:record:end -->\n"
    )
    assert record_of(store, "1") == backend.Record(
        key="5", waiting_for=None, token_hash=None
    )


def test_adopt_second_ticket_gets_key_after_first() -> None:
    # GIVEN
    store = make_store(["1", "2"])
    # WHEN
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    # THEN
    assert record_of(store, "1").key == "5"
    assert record_of(store, "2").key == "75"


def test_adopt_many_tickets_rebalances_keys_that_grow_too_long() -> None:
    # GIVEN
    numbers = [str(index + 1) for index in range(60)]
    store = make_store(numbers)
    # WHEN
    for number in numbers:
        backend.adopt_ticket(store, number)
    keys = [record_of(store, number).key for number in numbers]
    claimed = [backend.claim_ticket(store, "Backlog").ticket for _ in numbers]
    # THEN
    assert max(len(key) for key in keys) <= 24
    assert len(set(keys)) == len(numbers)
    assert claimed == numbers


def test_adopt_rebalance_preserves_claims_and_waiting_states() -> None:
    # GIVEN
    numbers = [str(index + 1) for index in range(60)]
    store = make_store(numbers)
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    first_claim = backend.claim_ticket(store, "Backlog")
    second_claim = backend.claim_ticket(store, "Backlog")
    backend.transition_ticket(store, "2", "In Progress", second_claim.token)
    first_hash = hashlib.sha256(first_claim.token.encode()).hexdigest()
    # WHEN
    for number in numbers[2:]:
        backend.adopt_ticket(store, number)
    keys = [record_of(store, number).key for number in numbers]
    first_issue = store.get_issue("1")
    second_issue = store.get_issue("2")
    # THEN
    assert max(len(key) for key in keys) <= 24
    assert len(set(keys)) == len(numbers)
    assert record_of(store, "1").waiting_for is None
    assert record_of(store, "1").token_hash == first_hash
    assert record_of(store, "2").waiting_for == "In Progress"
    assert record_of(store, "2").token_hash is None
    assert first_issue is not None
    assert first_issue.labels == ("workpull:Backlog",)
    assert second_issue is not None
    assert second_issue.labels == ("workpull:Backlog",)
    assert backend.list_waiting(store, "In Progress") == ("2",)
    assert backend.release_ticket(store, "1", first_claim.token) == "1"


class AdoptFailureCase(NamedTuple):
    case_name: str
    pre_adopted: str | None
    ticket: str
    expected_labels: tuple[str, ...]


def _adopt_failure_case_id(case: AdoptFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        AdoptFailureCase(
            case_name="already_adopted",
            pre_adopted="1",
            ticket="1",
            expected_labels=("workpull:Backlog",),
        ),
        AdoptFailureCase(
            case_name="unknown_issue",
            pre_adopted=None,
            ticket="9",
            expected_labels=(),
        ),
    ],
    ids=_adopt_failure_case_id,
)
def test_adopt_failures_change_nothing(case: AdoptFailureCase) -> None:
    # GIVEN
    store = make_store(["1"])
    if case.pre_adopted is not None:
        backend.adopt_ticket(store, case.pre_adopted)
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.adopt_ticket(store, case.ticket)
    issue = store.get_issue("1")
    assert issue is not None
    assert issue.labels == case.expected_labels


def test_discard_then_adopt_reuses_key_value_but_keeps_claim_order() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    first_claim = backend.claim_ticket(store, "Backlog")
    second_claim = backend.claim_ticket(store, "Backlog")
    backend.discard_ticket(store, "2", second_claim.token)
    # WHEN
    backend.adopt_ticket(store, "3")
    backend.release_ticket(store, "1", first_claim.token)
    claimed = [
        backend.claim_ticket(store, "Backlog").ticket,
        backend.claim_ticket(store, "Backlog").ticket,
    ]
    # THEN
    assert record_of(store, "3").key == "75"
    assert claimed == ["1", "3"]


def test_claim_picks_highest_priority_and_stores_only_token_hash() -> None:
    # GIVEN
    store = make_store(["1", "2"])
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    # WHEN
    claim = backend.claim_ticket(store, "Backlog")
    issue = store.get_issue("1")
    # THEN
    assert claim.ticket == "1"
    assert claim.token != ""
    assert issue is not None
    expected_hash = hashlib.sha256(claim.token.encode()).hexdigest()
    assert record_of(store, "1") == backend.Record(
        key="5", waiting_for=None, token_hash=expected_hash
    )
    assert claim.token not in issue.body
    assert record_of(store, "2").token_hash is None


def test_claim_skips_claimed_and_waiting_tickets() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    for number in ("1", "2", "3"):
        backend.adopt_ticket(store, number)
    first = backend.claim_ticket(store, "Backlog")
    second = backend.claim_ticket(store, "Backlog")
    backend.transition_ticket(store, "2", "In Progress", second.token)
    # WHEN
    third = backend.claim_ticket(store, "Backlog")
    # THEN
    assert first.ticket == "1"
    assert second.ticket == "2"
    assert third.ticket == "3"


def test_claim_with_no_available_ticket_fails() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    backend.claim_ticket(store, "Backlog")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.claim_ticket(store, "Backlog")


def test_release_with_wrong_token_fails_and_keeps_claim() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.release_ticket(store, "1", "wrong-token")
    assert (
        record_of(store, "1").token_hash
        == hashlib.sha256(claim.token.encode()).hexdigest()
    )


def test_release_clears_only_the_claim() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    # WHEN
    released = backend.release_ticket(store, "1", claim.token)
    issue = store.get_issue("1")
    # THEN
    assert released == "1"
    assert record_of(store, "1") == backend.Record(
        key="5", waiting_for=None, token_hash=None
    )
    assert issue is not None
    assert issue.labels == ("workpull:Backlog",)
    reclaimed = backend.claim_ticket(store, "Backlog")
    assert reclaimed.ticket == "1"


def test_transition_with_wrong_token_fails_and_changes_nothing() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.transition_ticket(store, "1", "In Progress", "wrong-token")
    assert record_of(store, "1") == backend.Record(
        key="5",
        waiting_for=None,
        token_hash=hashlib.sha256(claim.token.encode()).hexdigest(),
    )


def test_transition_writes_waiting_for_and_ends_claim() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    # WHEN
    moved = backend.transition_ticket(store, "1", "In Progress", claim.token)
    issue = store.get_issue("1")
    # THEN
    assert moved == "1"
    assert record_of(store, "1") == backend.Record(
        key="5", waiting_for="In Progress", token_hash=None
    )
    assert issue is not None
    assert issue.labels == ("workpull:Backlog",)
    assert backend.get_state(store, "1") == "In Progress"
    assert backend.count_state(store, "Backlog") == backend.StateCount(wait=0, work=1)
    assert backend.count_state(store, "In Progress") == backend.StateCount(
        wait=1, work=0
    )


def test_system_move_swaps_label_and_clears_waiting() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    backend.transition_ticket(store, "1", "In Progress", claim.token)
    # WHEN
    moved = backend.system_move(store, "1", "In Progress")
    issue = store.get_issue("1")
    # THEN
    assert moved == "1"
    assert issue is not None
    assert issue.labels == ("workpull:In Progress",)
    assert record_of(store, "1") == backend.Record(
        key="5", waiting_for=None, token_hash=None
    )
    assert backend.get_state(store, "1") == "In Progress"
    assert backend.count_state(store, "In Progress") == backend.StateCount(
        wait=0, work=1
    )


def test_system_move_for_a_state_the_ticket_does_not_wait_for_fails() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.system_move(store, "1", "In Progress")


def test_discard_with_wrong_token_fails_and_changes_nothing() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    backend.claim_ticket(store, "Backlog")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.discard_ticket(store, "1", "wrong-token")
    issue = store.get_issue("1")
    assert issue is not None
    assert issue.labels == ("workpull:Backlog",)
    assert backend.parse_record(issue.body) is not None


def test_discard_removes_record_and_label_together() -> None:
    # GIVEN
    store = make_store(["1"])
    backend.adopt_ticket(store, "1")
    claim = backend.claim_ticket(store, "Backlog")
    # WHEN
    discarded = backend.discard_ticket(store, "1", claim.token)
    issue = store.get_issue("1")
    # THEN
    assert discarded == "1"
    assert issue is not None
    assert issue.labels == ()
    assert issue.body == "Body of 1"
    assert backend.count_state(store, "Backlog") == backend.StateCount(wait=0, work=0)
    with pytest.raises(backend.AdapterFailure):
        backend.get_state(store, "1")
    with pytest.raises(backend.AdapterFailure):
        backend.release_ticket(store, "1", claim.token)


def test_get_state_of_unadopted_ticket_fails() -> None:
    # GIVEN
    store = make_store(["1"])
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.get_state(store, "1")


def test_list_waiting_returns_priority_order() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    for number in ("1", "2", "3"):
        backend.adopt_ticket(store, number)
        claim = backend.claim_ticket(store, "Backlog")
        backend.transition_ticket(store, number, "In Progress", claim.token)
    # WHEN
    waiting = backend.list_waiting(store, "In Progress")
    # THEN
    assert waiting == ("1", "2", "3")
    assert backend.list_waiting(store, "Done") == ()


def test_prioritize_top_moves_ticket_to_the_front() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    for number in ("1", "2", "3"):
        backend.adopt_ticket(store, number)
        claim = backend.claim_ticket(store, "Backlog")
        backend.transition_ticket(store, number, "In Progress", claim.token)
    # WHEN
    moved = backend.prioritize_ticket(store, "3", backend.TOP_SENTINEL)
    # THEN
    assert moved == "3"
    assert record_of(store, "3").key == "25"
    assert backend.list_waiting(store, "In Progress") == ("3", "1", "2")


def test_prioritize_after_anchor_uses_midpoint_to_next_ticket() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    for number in ("1", "2", "3"):
        backend.adopt_ticket(store, number)
    # WHEN
    moved = backend.prioritize_ticket(store, "1", "2")
    # THEN
    assert moved == "1"
    assert record_of(store, "1").key == "8125"
    claim = backend.claim_ticket(store, "Backlog")
    assert claim.ticket == "2"


def test_prioritize_after_last_ticket_goes_last() -> None:
    # GIVEN
    store = make_store(["1", "2"])
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    # WHEN
    backend.prioritize_ticket(store, "1", "2")
    # THEN
    assert record_of(store, "1").key == "875"
    claim = backend.claim_ticket(store, "Backlog")
    assert claim.ticket == "2"


def test_prioritize_preserves_claims_and_waiting_states() -> None:
    # GIVEN
    store = make_store(["1", "2", "3"])
    for number in ("1", "2", "3"):
        backend.adopt_ticket(store, number)
    first_claim = backend.claim_ticket(store, "Backlog")
    second_claim = backend.claim_ticket(store, "Backlog")
    backend.transition_ticket(store, "1", "In Progress", first_claim.token)
    second_hash = hashlib.sha256(second_claim.token.encode()).hexdigest()
    # WHEN
    backend.prioritize_ticket(store, "3", "1")
    backend.prioritize_ticket(store, "2", backend.TOP_SENTINEL)
    backend.prioritize_ticket(store, "1", "2")
    # THEN
    assert record_of(store, "1").waiting_for == "In Progress"
    assert record_of(store, "1").token_hash is None
    assert record_of(store, "2").waiting_for is None
    assert record_of(store, "2").token_hash == second_hash
    assert record_of(store, "3").waiting_for is None
    assert record_of(store, "3").token_hash is None
    assert backend.list_waiting(store, "In Progress") == ("1",)
    assert backend.release_ticket(store, "2", second_claim.token) == "2"


class PrioritizeFailureCase(NamedTuple):
    case_name: str
    ticket: str
    after: str


def _prioritize_failure_case_id(case: PrioritizeFailureCase) -> str:
    return case.case_name


@pytest.mark.parametrize(
    "case",
    [
        PrioritizeFailureCase(case_name="unknown_ticket", ticket="9", after="1"),
        PrioritizeFailureCase(case_name="unknown_anchor", ticket="1", after="9"),
        PrioritizeFailureCase(case_name="after_itself", ticket="1", after="1"),
        PrioritizeFailureCase(case_name="unadopted_ticket", ticket="2", after="1"),
    ],
    ids=_prioritize_failure_case_id,
)
def test_prioritize_failures_change_nothing(case: PrioritizeFailureCase) -> None:
    # GIVEN
    store = make_store(["1", "2"])
    backend.adopt_ticket(store, "1")
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        backend.prioritize_ticket(store, case.ticket, case.after)
    assert record_of(store, "1").key == "5"


def test_prioritize_rebalances_keys_that_grow_too_long() -> None:
    # GIVEN
    store = make_store(["1", "2"])
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    # WHEN
    last_moved = ""
    for index in range(200):
        last_moved = "1" if index % 2 == 0 else "2"
        backend.prioritize_ticket(store, last_moved, backend.TOP_SENTINEL)
    keys = [record_of(store, number).key for number in ("1", "2")]
    claim = backend.claim_ticket(store, "Backlog")
    # THEN
    assert max(len(key) for key in keys) <= 24
    assert len(set(keys)) == 2
    assert claim.ticket == last_moved


def test_prioritize_rebalance_preserves_claims_and_waiting_states() -> None:
    # GIVEN
    store = make_store(["1", "2"])
    backend.adopt_ticket(store, "1")
    backend.adopt_ticket(store, "2")
    first_claim = backend.claim_ticket(store, "Backlog")
    second_claim = backend.claim_ticket(store, "Backlog")
    backend.transition_ticket(store, "2", "In Progress", second_claim.token)
    first_hash = hashlib.sha256(first_claim.token.encode()).hexdigest()
    # WHEN
    for index in range(200):
        moved = "1" if index % 2 == 0 else "2"
        backend.prioritize_ticket(store, moved, backend.TOP_SENTINEL)
    keys = [record_of(store, number).key for number in ("1", "2")]
    first_issue = store.get_issue("1")
    second_issue = store.get_issue("2")
    # THEN
    assert max(len(key) for key in keys) <= 24
    assert len(set(keys)) == 2
    assert record_of(store, "1").waiting_for is None
    assert record_of(store, "1").token_hash == first_hash
    assert record_of(store, "2").waiting_for == "In Progress"
    assert record_of(store, "2").token_hash is None
    assert first_issue is not None
    assert first_issue.labels == ("workpull:Backlog",)
    assert second_issue is not None
    assert second_issue.labels == ("workpull:Backlog",)
    assert backend.list_waiting(store, "In Progress") == ("2",)
    assert backend.release_ticket(store, "1", first_claim.token) == "1"


def test_adopt_preserves_the_rest_of_the_body() -> None:
    # GIVEN
    store = FakeGithubStore(
        CONFIG,
        [
            backend.Issue(
                number="1",
                body="First line\nSecond line\n",
                labels=("unrelated",),
            )
        ],
    )
    # WHEN
    backend.adopt_ticket(store, "1")
    issue = store.get_issue("1")
    # THEN
    assert issue is not None
    assert issue.body.startswith("First line\nSecond line\n")
    assert issue.labels == ("unrelated", "workpull:Backlog")


HttpHandler = Callable[[urllib.request.Request], bytes]


class FakeHttpTransport:
    """Fake HTTP opener: records requests, replies via a handler.

    The handler returns the response body bytes, or raises
    urllib.error.HTTPError to simulate an HTTP error status.
    No network is touched.
    """

    def __init__(self, handler: HttpHandler) -> None:
        self._handler = handler
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request) -> io.BytesIO:
        self.requests.append(request)
        return io.BytesIO(self._handler(request))


def make_http_store(
    handler: HttpHandler,
) -> tuple[backend.HttpGithubStore, FakeHttpTransport]:
    transport = FakeHttpTransport(handler)
    store = backend.HttpGithubStore(
        repo="owner/repo",
        token="test-token",
        api_url="https://api.example.test",
        opener=transport,
    )
    return store, transport


def http_error(request: urllib.request.Request, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        request.full_url, code, "error", email.message.Message(), None
    )


def test_http_read_config_decodes_base64_contents() -> None:
    # GIVEN
    encoded = base64.b64encode(CONFIG.encode()).decode()
    wrapped = "\n".join(
        encoded[index : index + 10] for index in range(0, len(encoded), 10)
    )

    def handler(request: urllib.request.Request) -> bytes:
        return json.dumps({"content": wrapped}).encode()

    store, transport = make_http_store(handler)
    # WHEN
    actual = store.read_config()
    # THEN
    assert actual == CONFIG
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == "GET"
    assert request.full_url == (
        "https://api.example.test/repos/owner/repo/contents/workpull.toml"
    )
    assert request.get_header("Authorization") == "Bearer test-token"
    assert request.get_header("Accept") == "application/vnd.github+json"


def test_http_get_issue_parses_issue_labels_and_body() -> None:
    # GIVEN
    def handler(request: urllib.request.Request) -> bytes:
        return json.dumps(
            {
                "number": 7,
                "body": "Seventh body",
                "labels": [{"name": "workpull:Backlog"}, {"name": "other"}],
            }
        ).encode()

    store, transport = make_http_store(handler)
    # WHEN
    actual = store.get_issue("7")
    # THEN
    assert actual == backend.Issue(
        number="7", body="Seventh body", labels=("workpull:Backlog", "other")
    )
    assert transport.requests[0].full_url == (
        "https://api.example.test/repos/owner/repo/issues/7"
    )


def test_http_get_issue_missing_issue_returns_none() -> None:
    # GIVEN
    def handler(request: urllib.request.Request) -> bytes:
        raise http_error(request, 404)

    store, _transport = make_http_store(handler)
    # WHEN / THEN
    assert store.get_issue("9") is None


def test_http_get_issue_server_error_is_a_backend_failure() -> None:
    # GIVEN
    def handler(request: urllib.request.Request) -> bytes:
        raise http_error(request, 500)

    store, _transport = make_http_store(handler)
    # WHEN / THEN
    with pytest.raises(backend.AdapterFailure):
        store.get_issue("9")


def test_http_list_issues_paginates_with_open_state_filter() -> None:
    # GIVEN
    def handler(request: urllib.request.Request) -> bytes:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        assert query["state"] == ["open"]
        assert query["per_page"] == ["100"]
        page = int(query["page"][0])
        numbers = range(1, 101) if page == 1 else range(101, 103)
        return json.dumps(
            [
                {"number": number, "body": f"Body of {number}", "labels": []}
                for number in numbers
            ]
        ).encode()

    store, transport = make_http_store(handler)
    # WHEN
    issues = store.list_issues()
    # THEN
    assert [issue.number for issue in issues] == [
        str(number) for number in range(1, 103)
    ]
    assert len(transport.requests) == 2
    pages = [
        urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["page"]
        for request in transport.requests
    ]
    assert pages == [["1"], ["2"]]


def test_http_update_issue_sends_patch_with_body_and_labels() -> None:
    # GIVEN
    def handler(request: urllib.request.Request) -> bytes:
        return b"{}"

    store, transport = make_http_store(handler)
    # WHEN
    store.update_issue(
        backend.Issue(number="7", body="New body", labels=("workpull:Backlog",))
    )
    # THEN
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == "PATCH"
    assert request.full_url == "https://api.example.test/repos/owner/repo/issues/7"
    assert request.get_header("Content-type") == "application/json"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "body": "New body",
        "labels": ["workpull:Backlog"],
    }


def test_http_closed_adopted_issue_drops_out_of_list_operations() -> None:
    # GIVEN
    adopted_body = (
        "Closed issue\n"
        "\n"
        "<!-- workpull:record:start -->\n"
        "```toml\n"
        'key = "5"\n'
        'waiting_for = "In Progress"\n'
        "```\n"
        "<!-- workpull:record:end -->\n"
    )
    dataset = [
        {
            "number": 4,
            "body": adopted_body,
            "labels": [{"name": "workpull:Backlog"}],
            "state": "closed",
        }
    ]

    def handler(request: urllib.request.Request) -> bytes:
        parsed = urllib.parse.urlparse(request.full_url)
        if parsed.path.endswith("/issues"):
            query = urllib.parse.parse_qs(parsed.query)
            visible = [
                item
                for item in dataset
                if query["state"] != ["open"] or item["state"] == "open"
            ]
            return json.dumps(visible).encode()
        return json.dumps(dataset[0]).encode()

    store, _transport = make_http_store(handler)
    # WHEN / THEN
    assert store.get_issue("4") is not None
    assert backend.count_state(store, "Backlog") == backend.StateCount(wait=0, work=0)
    assert backend.list_waiting(store, "In Progress") == ()
    with pytest.raises(backend.AdapterFailure):
        backend.claim_ticket(store, "Backlog")


def write_file_store(
    numbers: list[str],
) -> None:
    Path("github_state.json").write_text(
        json.dumps(
            {
                "config": CONFIG,
                "issues": [
                    {"number": number, "body": f"Body of {number}", "labels": []}
                    for number in numbers
                ],
            }
        )
    )


def test_run_hooks_against_file_store(
    isolated_filesystem: IsolatedFilesystem,
) -> None:
    # GIVEN
    with isolated_filesystem():
        write_file_store(["1", "2"])
        base_env = {"WORKPULL_GITHUB_STATE_FILE": "github_state.json"}
        # WHEN
        describe = backend.run_describe(base_env)
        adopt_env = dict(base_env)
        adopt_env["WORKPULL_TICKET"] = "1"
        adopt = backend.run_adopt(adopt_env)
        count_env = dict(base_env)
        count_env["WORKPULL_STATE"] = "Backlog"
        count = backend.run_count(count_env)
        claim_env = dict(base_env)
        claim_env["WORKPULL_STATE"] = "Backlog"
        claim_code, claim_output = backend.run_claim_ticket(claim_env)
        claim = tomllib.loads(claim_output)
        state_env = dict(base_env)
        state_env["WORKPULL_TICKET"] = "1"
        state = backend.run_get_state(state_env)
        stored = Path("github_state.json").read_text()
    # THEN
    assert describe == (0, CONFIG)
    assert adopt == (0, "1\n")
    assert count == (0, "wait = 0\nwork = 1\n")
    assert claim_code == 0
    assert claim["ticket"] == "1"
    assert claim["token"] != ""
    assert claim["token"] not in stored
    assert hashlib.sha256(claim["token"].encode()).hexdigest() in stored
    assert state == (0, "Backlog\n")


def test_run_adopt_with_missing_context_fails() -> None:
    # GIVEN
    env = {"WORKPULL_GITHUB_STATE_FILE": "github_state.json"}
    # WHEN
    actual = backend.run_adopt(env)
    # THEN
    assert actual == (1, "")


def test_run_hooks_without_a_store_fail() -> None:
    # GIVEN
    env = {"WORKPULL_TICKET": "1"}
    # WHEN
    actual = backend.run_adopt(env)
    # THEN
    assert actual == (1, "")


def test_hook_script_adopt_via_subprocess(
    isolated_filesystem: IsolatedFilesystem,
) -> None:
    # GIVEN
    with isolated_filesystem():
        write_file_store(["1"])
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("WORKPULL_")
        }
        env["WORKPULL_GITHUB_STATE_FILE"] = "github_state.json"
        env["WORKPULL_TICKET"] = "1"
        # WHEN
        first = subprocess.run(
            [sys.executable, str(ADAPTER_DIR / "adopt.py")],
            env=env,
            capture_output=True,
            text=True,
        )
        second = subprocess.run(
            [sys.executable, str(ADAPTER_DIR / "adopt.py")],
            env=env,
            capture_output=True,
            text=True,
        )
    # THEN
    assert first.returncode == 0
    assert first.stdout == "1\n"
    assert second.returncode == 1
    assert second.stdout == ""
