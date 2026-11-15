"""Shared backend for the live GitHub adapter hooks.

One hook script per hook calls one run function here.
The run functions read context only from WORKPULL_*
environment variables, do the operation against a
GitHub layer, and return the exit code and stdout the
hook prints: exit 0 with the output means the
operation happened, exit 1 with no output means it
did not.

The GitHub layer is fakeable: WORKPULL_GITHUB_STATE_FILE
selects the file-backed store the tests use, and
GITHUB_REPOSITORY selects the live REST store, with
the credential in GITHUB_TOKEN. No test uses the live
store and no secret is stored in this repo.

Per-ticket data lives on the issue itself: the state
is the workpull: label, and the priority key, the
waiting-for state, and the claim token's SHA-256 hash
live in the marked TOML block in the issue body. The
plaintext token is returned once, by the claim hook,
and is never stored.
"""

import base64
import hashlib
import hmac
import json
import secrets
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any, NamedTuple, override

STATE_LABEL_PREFIX = "workpull:"
RECORD_START = "<!-- workpull:record:start -->"
RECORD_END = "<!-- workpull:record:end -->"
TOP_SENTINEL = "WORKPULL_TOP"
MAX_KEY_LENGTH = 24


class AdapterFailure(Exception):
    """The operation did not happen; the hook exits non-zero."""


class _HttpNotFound(AdapterFailure):
    """GitHub answered 404: the named resource does not exist."""


class Issue(NamedTuple):
    number: str
    body: str
    labels: tuple[str, ...]


class Record(NamedTuple):
    key: str
    waiting_for: str | None
    token_hash: str | None


class Claim(NamedTuple):
    ticket: str
    token: str


class StateCount(NamedTuple):
    wait: int
    work: int


class GithubStore:
    """The GitHub layer the adapter operations read and write."""

    def read_config(self) -> str:
        raise NotImplementedError

    def get_issue(self, number: str) -> Issue | None:
        raise NotImplementedError

    def list_issues(self) -> list[Issue]:
        raise NotImplementedError

    def update_issue(self, issue: Issue) -> None:
        raise NotImplementedError


def _json_str(value: Any) -> str:
    if not isinstance(value, str):
        raise AdapterFailure("unexpected GitHub value")
    return value


def _issue_from_json(item: Any) -> Issue:
    if not isinstance(item, dict):
        raise AdapterFailure("unexpected GitHub issue")
    number = item.get("number")
    if isinstance(number, int):
        number_text = str(number)
    else:
        number_text = _json_str(number)
    body_value = item.get("body")
    body = "" if body_value is None else _json_str(body_value)
    labels_value = item.get("labels")
    if not isinstance(labels_value, list):
        raise AdapterFailure("unexpected GitHub labels")
    labels: list[str] = []
    for label in labels_value:
        if isinstance(label, dict):
            labels.append(_json_str(label.get("name")))
        else:
            labels.append(_json_str(label))
    return Issue(number=number_text, body=body, labels=tuple(labels))


class FileGithubStore(GithubStore):
    """A GitHub layer backed by one JSON file, for tests.

    The file holds the repository config text and the
    issues, each with a number, a body, and label names.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError) as exc:
            raise AdapterFailure("cannot read GitHub state file") from exc
        if not isinstance(data, dict):
            raise AdapterFailure("unexpected GitHub state file")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self._path.write_text(json.dumps(data))

    @override
    def read_config(self) -> str:
        return _json_str(self._load().get("config"))

    @override
    def get_issue(self, number: str) -> Issue | None:
        for issue in self.list_issues():
            if issue.number == number:
                return issue
        return None

    @override
    def list_issues(self) -> list[Issue]:
        raw = self._load().get("issues")
        if not isinstance(raw, list):
            raise AdapterFailure("unexpected GitHub state file")
        return [_issue_from_json(item) for item in raw]

    @override
    def update_issue(self, issue: Issue) -> None:
        data = self._load()
        raw = data.get("issues")
        if not isinstance(raw, list):
            raise AdapterFailure("unexpected GitHub state file")
        for item in raw:
            if isinstance(item, dict) and str(item.get("number")) == issue.number:
                item["body"] = issue.body
                item["labels"] = list(issue.labels)
        self._save(data)


class HttpGithubStore(GithubStore):
    """The live GitHub layer: the REST API over stdlib urllib."""

    def __init__(
        self,
        repo: str,
        token: str,
        api_url: str,
        opener: Callable[[urllib.request.Request], Any],
    ) -> None:
        self._repo = repo
        self._token = token
        self._api_url = api_url
        self._opener = opener

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self._api_url.rstrip("/") + path, data=data, method=method
        )
        request.add_header("Accept", "application/vnd.github+json")
        if self._token:
            request.add_header("Authorization", f"Bearer {self._token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener(request) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _HttpNotFound("GitHub resource not found") from exc
            raise AdapterFailure("GitHub request failed") from exc
        except (urllib.error.URLError, ValueError) as exc:
            raise AdapterFailure("GitHub request failed") from exc

    @override
    def read_config(self) -> str:
        payload = self._request(
            "GET", f"/repos/{self._repo}/contents/workpull.toml", None
        )
        if not isinstance(payload, dict):
            raise AdapterFailure("unexpected GitHub config")
        encoded = _json_str(payload.get("content"))
        return base64.b64decode(encoded).decode()

    @override
    def get_issue(self, number: str) -> Issue | None:
        try:
            payload = self._request("GET", f"/repos/{self._repo}/issues/{number}", None)
        except _HttpNotFound:
            return None
        return _issue_from_json(payload)

    @override
    def list_issues(self) -> list[Issue]:
        issues: list[Issue] = []
        page = 1
        while True:
            payload = self._request(
                "GET",
                f"/repos/{self._repo}/issues?state=open&per_page=100&page={page}",
                None,
            )
            if not isinstance(payload, list):
                raise AdapterFailure("unexpected GitHub issues")
            issues.extend(_issue_from_json(item) for item in payload)
            if len(payload) < 100:
                return issues
            page += 1

    @override
    def update_issue(self, issue: Issue) -> None:
        self._request(
            "PATCH",
            f"/repos/{self._repo}/issues/{issue.number}",
            {"body": issue.body, "labels": list(issue.labels)},
        )


def store_from_env(env: Mapping[str, str]) -> GithubStore:
    state_file = env.get("WORKPULL_GITHUB_STATE_FILE")
    if state_file:
        return FileGithubStore(Path(state_file))
    repo = env.get("GITHUB_REPOSITORY")
    if repo:
        return HttpGithubStore(
            repo=repo,
            token=env.get("GITHUB_TOKEN", ""),
            api_url=env.get("GITHUB_API_URL", "https://api.github.com"),
            opener=urllib.request.urlopen,
        )
    raise AdapterFailure("no GitHub store is configured")


def parse_record(body: str) -> Record | None:
    start = body.find(RECORD_START)
    if start < 0:
        return None
    end = body.find(RECORD_END, start)
    if end < 0:
        return None
    segment = body[start:end]
    fence_start = segment.find("```toml")
    fence_end = segment.find("```", fence_start + 7)
    if fence_start < 0 or fence_end < 0:
        raise AdapterFailure("malformed workpull record")
    try:
        data = tomllib.loads(segment[fence_start + 7 : fence_end])
    except tomllib.TOMLDecodeError as exc:
        raise AdapterFailure("malformed workpull record") from exc
    key = data.get("key")
    if not isinstance(key, str):
        raise AdapterFailure("malformed workpull record")
    waiting_for = data.get("waiting_for")
    if waiting_for is not None and not isinstance(waiting_for, str):
        raise AdapterFailure("malformed workpull record")
    token_hash = data.get("token_hash")
    if token_hash is not None and not isinstance(token_hash, str):
        raise AdapterFailure("malformed workpull record")
    return Record(key=key, waiting_for=waiting_for, token_hash=token_hash)


def _record_block(record: Record) -> str:
    lines = [f'key = "{record.key}"']
    if record.waiting_for is not None:
        lines.append(f'waiting_for = "{record.waiting_for}"')
    if record.token_hash is not None:
        lines.append(f'token_hash = "{record.token_hash}"')
    return RECORD_START + "\n```toml\n" + "\n".join(lines) + "\n```\n" + RECORD_END


def render_body(body: str, record: Record | None) -> str:
    start = body.find(RECORD_START)
    if start >= 0:
        end = body.find(RECORD_END, start) + len(RECORD_END)
        if record is None:
            before = body[:start]
            after = body[end:]
            if after.startswith("\n"):
                after = after[1:]
            if before.endswith("\n\n"):
                before = before[:-2]
            return before + after
        return body[:start] + _record_block(record) + body[end:]
    if record is None:
        return body
    block = _record_block(record) + "\n"
    if body == "":
        return block
    if body.endswith("\n"):
        return body + "\n" + block
    return body + "\n\n" + block


def state_of(issue: Issue) -> str | None:
    for label in issue.labels:
        if label.startswith(STATE_LABEL_PREFIX):
            return label[len(STATE_LABEL_PREFIX) :]
    return None


def _key_to_fraction(key: str) -> Fraction:
    return Fraction(int(key), 10 ** len(key))


def _fraction_to_key(value: Fraction) -> str:
    scale = 1
    while (value * scale).denominator != 1:
        scale *= 10
    scaled = (value * scale).numerator
    digits = str(scaled).rjust(len(str(scale)) - 1, "0")
    return digits.rstrip("0") or "0"


def key_between(low_key: str | None, high_key: str | None) -> str:
    low = Fraction(0) if low_key is None else _key_to_fraction(low_key)
    high = Fraction(1) if high_key is None else _key_to_fraction(high_key)
    return _fraction_to_key((low + high) / 2)


def _require_issue(store: GithubStore, ticket: str) -> Issue:
    issue = store.get_issue(ticket)
    if issue is None:
        raise AdapterFailure(f"unknown issue: {ticket}")
    return issue


def _require_record(issue: Issue) -> Record:
    record = parse_record(issue.body)
    if record is None:
        raise AdapterFailure(f"ticket is not adopted: {issue.number}")
    return record


def _adopted(store: GithubStore) -> list[tuple[Issue, Record]]:
    adopted: list[tuple[Issue, Record]] = []
    for issue in store.list_issues():
        if state_of(issue) is None:
            continue
        adopted.append((issue, _require_record(issue)))
    return adopted


def _first_state(store: GithubStore) -> str:
    try:
        view = tomllib.loads(store.read_config())
    except tomllib.TOMLDecodeError as exc:
        raise AdapterFailure("malformed workpull.toml") from exc
    states = view.get("states")
    if not isinstance(states, list) or not states:
        raise AdapterFailure("malformed workpull.toml")
    first = states[0]
    if not isinstance(first, str):
        raise AdapterFailure("malformed workpull.toml")
    return first


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_token(issue: Issue, token: str) -> Record:
    record = _require_record(issue)
    if record.token_hash is None or not hmac.compare_digest(
        record.token_hash, _token_hash(token)
    ):
        raise AdapterFailure("token does not match the claim")
    return record


def _save_record(store: GithubStore, issue: Issue, record: Record) -> None:
    store.update_issue(
        Issue(
            number=issue.number,
            body=render_body(issue.body, record),
            labels=issue.labels,
        )
    )


def describe_output(store: GithubStore) -> str:
    return store.read_config()


def adopt_ticket(store: GithubStore, ticket: str) -> str:
    issue = _require_issue(store, ticket)
    if state_of(issue) is not None:
        raise AdapterFailure(f"ticket is already adopted: {ticket}")
    adopted = _adopted(store)
    keys = [record.key for _, record in adopted]
    key = key_between(max(keys) if keys else None, None)
    record = Record(key=key, waiting_for=None, token_hash=None)
    first_label = STATE_LABEL_PREFIX + _first_state(store)
    if len(key) > MAX_KEY_LENGTH:
        ordered = sorted(adopted, key=lambda pair: pair[1].key) + [(issue, record)]
        for (target, target_record), spread_key in zip(
            ordered, _spread_keys(len(ordered)), strict=True
        ):
            spread_record = Record(
                key=spread_key,
                waiting_for=target_record.waiting_for,
                token_hash=target_record.token_hash,
            )
            if target.number == ticket:
                store.update_issue(
                    Issue(
                        number=target.number,
                        body=render_body(target.body, spread_record),
                        labels=target.labels + (first_label,),
                    )
                )
            else:
                _save_record(store, target, spread_record)
        return ticket
    store.update_issue(
        Issue(
            number=issue.number,
            body=render_body(issue.body, record),
            labels=issue.labels + (first_label,),
        )
    )
    return ticket


def _spread_keys(count: int) -> list[str]:
    denominator = 10 ** len(str(count))
    step = denominator // (count + 1)
    return [
        _fraction_to_key(Fraction((index + 1) * step, denominator))
        for index in range(count)
    ]


def prioritize_ticket(store: GithubStore, ticket: str, after: str) -> str:
    issue = _require_issue(store, ticket)
    _require_record(issue)
    others = [
        (other, record) for other, record in _adopted(store) if other.number != ticket
    ]
    others.sort(key=lambda pair: pair[1].key)
    if after == TOP_SENTINEL:
        position = 0
        new_key = key_between(None, others[0][1].key if others else None)
    else:
        if after == ticket:
            raise AdapterFailure("a ticket cannot move after itself")
        anchor = _require_issue(store, after)
        _require_record(anchor)
        anchor_index = next(
            index for index, (other, _) in enumerate(others) if other.number == after
        )
        position = anchor_index + 1
        next_key = (
            others[anchor_index + 1][1].key if anchor_index + 1 < len(others) else None
        )
        new_key = key_between(others[anchor_index][1].key, next_key)
    if len(new_key) > MAX_KEY_LENGTH:
        ordered = (
            others[:position] + [(issue, _require_record(issue))] + others[position:]
        )
        for (target, record), spread_key in zip(
            ordered, _spread_keys(len(ordered)), strict=True
        ):
            _save_record(
                store,
                target,
                Record(
                    key=spread_key,
                    waiting_for=record.waiting_for,
                    token_hash=record.token_hash,
                ),
            )
        return ticket
    record = _require_record(issue)
    _save_record(
        store,
        issue,
        Record(
            key=new_key,
            waiting_for=record.waiting_for,
            token_hash=record.token_hash,
        ),
    )
    return ticket


def claim_ticket(store: GithubStore, state: str) -> Claim:
    candidates = [
        (issue, record)
        for issue, record in _adopted(store)
        if state_of(issue) == state
        and record.waiting_for is None
        and record.token_hash is None
    ]
    if not candidates:
        raise AdapterFailure(f"no claimable ticket in state: {state}")
    candidates.sort(key=lambda pair: pair[1].key)
    issue, record = candidates[0]
    token = secrets.token_hex(16)
    _save_record(
        store,
        issue,
        Record(
            key=record.key,
            waiting_for=record.waiting_for,
            token_hash=_token_hash(token),
        ),
    )
    return Claim(ticket=issue.number, token=token)


def release_ticket(store: GithubStore, ticket: str, token: str) -> str:
    issue = _require_issue(store, ticket)
    record = _validate_token(issue, token)
    _save_record(
        store,
        issue,
        Record(key=record.key, waiting_for=record.waiting_for, token_hash=None),
    )
    return ticket


def transition_ticket(
    store: GithubStore, ticket: str, to_state: str, token: str
) -> str:
    issue = _require_issue(store, ticket)
    record = _validate_token(issue, token)
    _save_record(
        store,
        issue,
        Record(key=record.key, waiting_for=to_state, token_hash=None),
    )
    return ticket


def discard_ticket(store: GithubStore, ticket: str, token: str) -> str:
    issue = _require_issue(store, ticket)
    _validate_token(issue, token)
    store.update_issue(
        Issue(
            number=issue.number,
            body=render_body(issue.body, None),
            labels=tuple(
                label
                for label in issue.labels
                if not label.startswith(STATE_LABEL_PREFIX)
            ),
        )
    )
    return ticket


def count_state(store: GithubStore, state: str) -> StateCount:
    work = 0
    wait = 0
    for issue in store.list_issues():
        if state_of(issue) == state:
            work += 1
        record = parse_record(issue.body)
        if record is not None and record.waiting_for == state:
            wait += 1
    return StateCount(wait=wait, work=work)


def get_state(store: GithubStore, ticket: str) -> str:
    issue = _require_issue(store, ticket)
    state = state_of(issue)
    if state is None:
        raise AdapterFailure(f"ticket is not adopted: {ticket}")
    record = parse_record(issue.body)
    if record is not None and record.waiting_for is not None:
        return record.waiting_for
    return state


def list_waiting(store: GithubStore, state: str) -> tuple[str, ...]:
    waiting = [
        (issue, record)
        for issue, record in _adopted(store)
        if record.waiting_for == state
    ]
    waiting.sort(key=lambda pair: pair[1].key)
    return tuple(issue.number for issue, _ in waiting)


def system_move(store: GithubStore, ticket: str, to_state: str) -> str:
    issue = _require_issue(store, ticket)
    record = _require_record(issue)
    if record.waiting_for != to_state:
        raise AdapterFailure(f"ticket is not waiting for: {to_state}")
    labels = tuple(
        STATE_LABEL_PREFIX + to_state if label.startswith(STATE_LABEL_PREFIX) else label
        for label in issue.labels
    )
    store.update_issue(
        Issue(
            number=issue.number,
            body=render_body(
                issue.body,
                Record(key=record.key, waiting_for=None, token_hash=record.token_hash),
            ),
            labels=labels,
        )
    )
    return ticket


def _require_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not value:
        raise AdapterFailure(f"{name} is not set")
    return value


def run_describe(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        return (0, describe_output(store_from_env(env)))
    except AdapterFailure:
        return (1, "")


def run_adopt(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        return (0, adopt_ticket(store_from_env(env), ticket) + "\n")
    except AdapterFailure:
        return (1, "")


def run_prioritize(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        after = _require_env(env, "WORKPULL_AFTER")
        return (0, prioritize_ticket(store_from_env(env), ticket, after) + "\n")
    except AdapterFailure:
        return (1, "")


def run_claim_ticket(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        state = _require_env(env, "WORKPULL_STATE")
        claim = claim_ticket(store_from_env(env), state)
        return (0, f'ticket = "{claim.ticket}"\ntoken = "{claim.token}"\n')
    except AdapterFailure:
        return (1, "")


def run_release(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        token = _require_env(env, "WORKPULL_TOKEN")
        return (0, release_ticket(store_from_env(env), ticket, token) + "\n")
    except AdapterFailure:
        return (1, "")


def run_transition(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        to_state = _require_env(env, "WORKPULL_TO_STATE")
        token = _require_env(env, "WORKPULL_TOKEN")
        result = transition_ticket(store_from_env(env), ticket, to_state, token)
        return (0, result + "\n")
    except AdapterFailure:
        return (1, "")


def run_discard(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        token = _require_env(env, "WORKPULL_TOKEN")
        return (0, discard_ticket(store_from_env(env), ticket, token) + "\n")
    except AdapterFailure:
        return (1, "")


def run_count(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        state = _require_env(env, "WORKPULL_STATE")
        counts = count_state(store_from_env(env), state)
        return (0, f"wait = {counts.wait}\nwork = {counts.work}\n")
    except AdapterFailure:
        return (1, "")


def run_get_state(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        return (0, get_state(store_from_env(env), ticket) + "\n")
    except AdapterFailure:
        return (1, "")


def run_list_waiting(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        state = _require_env(env, "WORKPULL_STATE")
        tickets = list_waiting(store_from_env(env), state)
        names = ", ".join(f'"{ticket}"' for ticket in tickets)
        return (0, f"tickets = [{names}]\n")
    except AdapterFailure:
        return (1, "")


def run_system_move(env: Mapping[str, str]) -> tuple[int, str]:
    try:
        ticket = _require_env(env, "WORKPULL_TICKET")
        to_state = _require_env(env, "WORKPULL_TO_STATE")
        return (0, system_move(store_from_env(env), ticket, to_state) + "\n")
    except AdapterFailure:
        return (1, "")
