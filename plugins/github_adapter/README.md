# GitHub adapter

A ready-made Workpull backend for GitHub Issues in one
repository. One hook script per hook lives here, backed
by the shared module `github_backend.py`. Workpull core
knows nothing about GitHub; the hooks are set in the
environment exactly like any other backend's hooks.

## Setup

Write `workpull.toml` at the target repository root, in
the describe shape: `states` in workflow order,
`[transitions]`, and `[wip_limits]` with exactly `work`
and `wait` per state. The describe hook reads that file
through the GitHub API and prints it.

Set the repository and credential in the environment
the hooks inherit:

- `GITHUB_REPOSITORY`: the target repository, as
  `owner/name`.
- `GITHUB_TOKEN`: a credential with write access to
  the repository's issues. Every operator's hooks must
  be able to edit issue bodies, because the per-ticket
  record lives in the body.
- `GITHUB_API_URL`: optional, defaults to
  `https://api.github.com`.
- `WORKPULL_GITHUB_CONFIG_BRANCH`: optional, the
  branch `workpull.toml` is read from. When it is
  not set, the file is read from the repository's
  default branch.

Point each Workpull hook at the matching script,
replacing `<python>` with the Python 3.12 interpreter
and `<path>` with this directory's path:

- `DESCRIBE_HOOK="<python> <path>/describe.py"`
- `ADOPT_HOOK="<python> <path>/adopt.py"`
- `PRIORITIZE_HOOK="<python> <path>/prioritize.py"`
- `CLAIM_TICKET_HOOK="<python> <path>/claim_ticket.py"`
- `RELEASE_HOOK="<python> <path>/release.py"`
- `TRANSITION_HOOK="<python> <path>/transition.py"`
- `DISCARD_HOOK="<python> <path>/discard.py"`
- `COUNT_HOOK="<python> <path>/count.py"`
- `GET_STATE_HOOK="<python> <path>/get_state.py"`
- `LIST_WAITING_HOOK="<python> <path>/list_waiting.py"`
- `SYSTEM_MOVE_HOOK="<python> <path>/system_move.py"`

## How state is stored

- A ticket is one issue. The ticket id is the issue
  number, as a string.
- A workflow state is a label named `workpull:` plus
  the state name. An adopted ticket carries exactly
  one state label, naming its work state. GitHub
  creates a label that does not exist yet when it is
  first applied, so setup needs no label step.
- The adapter neither opens nor closes issues. The
  terminal workflow state is a `workpull:` label like
  any other.
- Everything else lives in one marked block in the
  issue body, between `<!-- workpull:record:start -->`
  and `<!-- workpull:record:end -->`: the priority
  order key (`key`), the state the ticket waits for
  (`waiting_for`, only while it waits), and the claim
  token's hash (`token_hash`, only while it is
  claimed). The adapter rewrites only that block; the
  rest of the body is left as it is.
- Priority keys are fractional order keys: decimal
  digit strings compared as fractions, never floats.
  A prioritize move computes the midpoint after the
  anchor ticket, `WORKPULL_TOP` computes a key before
  the first key, adopt assigns a key after every key
  already assigned, and keys are rebalanced back to
  short keys when they grow too long.
- The claim token is generated at claim time and
  returned once, in the claim hook's output. Only its
  SHA-256 hash, in hex, is stored. A lost token cannot
  be recovered from the record; clearing a stuck claim
  takes an operator editing the record by hand, outside
  Workpull.

## Tests

The adapter's tests run against a fake GitHub layer,
never the live API. Setting `WORKPULL_GITHUB_STATE_FILE`
to a JSON file selects the file-backed store the tests
use: the file holds the repository config text under
`config` and the issues under `issues`, each with a
`number`, a `body`, and `labels`.
