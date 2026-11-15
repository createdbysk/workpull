# Design 020 — GitHub adapter (live)

Status: complete draft. The state model, the
per-ticket storage, and the claim token's stored
form are decided (Satish, 2026-11-15). Everything
is settled.

## Scope

- Issue 17: Workpull ships with a ready-made GitHub
  adapter, so a user can run the Workpull commands
  against GitHub Issues in one repository without
  writing adapter scripts.
- This is the live adapter. `plugins/github/` today
  holds only the describe shape-validation mock of
  design 002, which is not a live backend adapter and
  stays as it is.
- Workpull core does not change. The adapter is a set
  of hook scripts, one per hook, set in the
  environment exactly like any other backend's hooks.
  The CLI knows nothing about GitHub.
- The adapter is built and dogfooded on branch 0.2,
  on top of 0.1. This record is the design pass only.

## Ticket

- A ticket is one GitHub issue in the repository.
- The ticket id the hooks carry is the issue number,
  as a string. Hooks carry ticket ids only; no title,
  body, or other issue text crosses the hook boundary.
- Workpull does not create issues. An issue is created
  in GitHub, then brought into Workpull by `adopt`,
  exactly as design 009 requires of every backend.

## Hook inventory

The adapter implements every hook the CLI can call,
with the contexts and outputs the existing designs
fix. Nothing here is adapter-specific; it is the
obligation list the rest of this design works
against.

- `DESCRIBE_HOOK` — no context. Prints the describe
  TOML: `states`, `[transitions]`, `[wip_limits]`
  with exactly `work` and `wait` per state.
- `ADOPT_HOOK` — `WORKPULL_TICKET`. Prints the
  ticket id.
- `PRIORITIZE_HOOK` — `WORKPULL_TICKET`,
  `WORKPULL_AFTER` (a ticket id, or the sentinel
  `WORKPULL_TOP`). Prints the ticket id.
- `CLAIM_TICKET_HOOK` — `WORKPULL_STATE`. Prints
  TOML with exactly `ticket` and `token`, each a
  non-empty string.
- `RELEASE_HOOK` — `WORKPULL_TICKET`,
  `WORKPULL_TOKEN`. Prints the ticket id.
- `TRANSITION_HOOK` — `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`, `WORKPULL_TOKEN`. Prints the
  ticket id.
- `DISCARD_HOOK` — `WORKPULL_TICKET`,
  `WORKPULL_TOKEN`. Prints the ticket id.
- `COUNT_HOOK` — `WORKPULL_STATE`. Prints TOML with
  exactly `wait` and `work`, each a non-negative
  integer.
- `GET_STATE_HOOK` — `WORKPULL_TICKET`. Prints the
  state name.
- `LIST_WAITING_HOOK` — `WORKPULL_STATE`. Prints
  TOML with exactly `tickets`, a list of ticket ids
  in priority order, first is highest.
- `SYSTEM_MOVE_HOOK` — `WORKPULL_TICKET`,
  `WORKPULL_TO_STATE`. No token: the system is the
  mover. Prints the ticket id.
- Everywhere: exit 0 means the operation happened,
  non-zero means it did not, and the CLI preserves
  the code. Context arrives only through environment
  variables, never interpolated into a command
  string. The hooks inherit the operator's
  environment, which is where the adapter's GitHub
  credential lives; no secret is stored in this repo.

## State model — decided: states are labels

Decided by Satish, 2026-11-15. This replaces Open
question 1 of the earlier draft; options A (Open and
Closed as the states) and C (Projects board columns)
are rejected and not reconsidered here.

- A workflow state is a GitHub label on the issue.
  The label's name is `workpull:` followed by the
  state name, verbatim: the state In Progress is the
  label `workpull:In Progress`. Every state label
  starts with the `workpull:` prefix, so Workpull's
  labels are visibly Workpull's and no other label is
  one. Stripping the fixed prefix leaves the state
  name, which obeys design 001's state-name rules.
- An adopted ticket carries exactly one state label,
  and it names the ticket's work state: the state the
  ticket is in work in, or the state it left and
  still counts against while it waits (designs 012,
  016). Waiting is not a state and gets no state
  label; the waiting-for record lives in the
  per-ticket record on the issue, below.
- GitHub's own Open and Closed are not Workpull
  states in this adapter. The terminal workflow state
  is a `workpull:` label like any other, and the
  adapter neither opens nor closes issues. Closing an
  issue is the operator's GitHub-side housekeeping,
  outside Workpull.
- Satish's ruling is the contract for hand-edited
  labels: the labels are the user's own setup, in
  their own repository. A user who adds, removes, or
  renames `workpull:` labels by hand is sabotaging
  their own Workpull setup; it is in their interest
  to make it work, and if they choose otherwise it
  is on them. The adapter reads the labels as they
  are. It does not defensively guard the cases
  hand-editing creates — an adopted issue left with
  no state label, or with several — and no reading
  is promised for them. They are outside the
  contract, the same way the core guards only
  API-level invariants on real scenarios, never
  manufactured ones.

## Describe — where the view comes from

The labels alone cannot source the describe view:
they record which state each ticket is in, but the
states list is ordered (a transition target must be
later than its source, design 001), and neither the
order, the transitions, nor the WIP limits are in
any label. So the view comes from configuration,
and the labels are its per-ticket record.

- When an operator sets Workpull up on a repository,
  they write one configuration file, `workpull.toml`,
  at the repository root, in the describe TOML shape
  of design 001: `states` in workflow order,
  `[transitions]`, and `[wip_limits]` with exactly
  `work` and `wait` per state. The states it names
  are the workflow's states, and each one is the
  `workpull:` label of the same name.
- The describe hook reads that file through the
  GitHub API and prints it. The CLI validates and
  normalizes it exactly as for any backend (design
  001). Because the file lives in the repository,
  every operator and every host sees the same
  states, transitions, and limits, which the
  distributed claim design requires (design 015).
- The adapter applies state labels by name; GitHub
  creates a label that does not exist yet when it is
  first applied to an issue, so setup needs no
  separate label-creation step.
- Editing `workpull.toml` by hand is the operator's
  own act, under the same ruling as the labels: the
  adapter reads it as it is, and the CLI's describe
  validation rejects a file that breaks the contract
  shape. A state label that the configuration does
  not name is a hand-edit case, above.

## State reads and writes, per operation

- Adopt adds the first state's label (the first
  state in the configuration's `states` list) to the
  issue. Adopting an issue that already carries a
  `workpull:` state label fails, per the settled
  adopt semantics below.
- Get-state reads the issue's labels and returns the
  name on its state label. For a waiting ticket it
  returns the waiting-for state instead (design
  013); that read goes to the per-ticket record.
- Count, for a state, counts issues carrying that
  state's label as `work` — a waiting ticket keeps
  its work state's label until the system move, so
  it is counted there, as design 012 requires — and
  counts tickets whose per-ticket record names the
  state as `wait`.
- Transition writes the waiting-for record (the
  to-state) and ends the claim. The state label does
  not change: the ticket still counts as work in the
  state it left.
- System move completes the move the transition
  started: it replaces the ticket's state label with
  the to-state's label and clears the waiting-for
  record. The pull sweep and the transition cascade
  compose count, list-waiting, and system-move
  exactly as designs 016 and 019 specify, so the
  adapter adds no pull logic of its own; only
  list-waiting's ordering reads the priority keys,
  from the per-ticket records.
- Discard removes the ticket's state label and its
  per-ticket record together: the ticket is in no
  state and counts against no state's WIP.
- Claim, release, and prioritize change no state
  label. Claim and release touch only the claim
  record; prioritize touches only the priority key.

## Settled semantics, per operation

These follow from the existing designs and the mock
backend in `tests/test_component.py`, the reference
implementation of the backend side.

### Priority

- Priority is backend-owned and invisible to
  Workpull: no hook receives or returns a priority
  value, and hooks carry ticket ids only. The
  backend keeps a total order over adopted tickets.
- The order key is a fractional order key, carried
  with the ticket in every state until the terminal
  state, per design 008 and the ticket lifetime
  record. Keys are strings or arbitrary-precision
  decimals, never floats; a move computes the
  midpoint after the anchor ticket, `WORKPULL_TOP`
  takes a key before the first key, and the order is
  rebalanced back to short keys when keys grow too
  long.
- The user controls priority only through
  `prioritize <ticket> <after|WORKPULL_TOP>`, one
  relative move at a time, like a board drag. There
  is no priority value for a user to type, by design.

### Adopt

- The adopt hook brings an existing issue into
  Workpull: it assigns the first state in the
  describe list, and an initial priority key after
  the maximum key among the tickets currently
  adopted, so adoption order among live tickets is
  priority order until a prioritize move changes
  it.
- Discard removes a ticket's record (see the
  per-ticket record section), so a discarded
  ticket's key value may later be assigned again
  to a newly adopted ticket. That reuse is not
  observable through the Workpull API: the
  discarded ticket is outside the system, and no
  hook receives or returns a key.
- Adopting an issue that is already adopted, or
  already in progress, fails: the hook exits
  non-zero.

### Claim

- The claim-ticket hook picks, among the tickets in
  the named state that are in work (not waiting) and
  unclaimed, the highest priority one, issues a
  token, stores the token with the claim, and
  returns `ticket` and `token` (designs 005, 015).
- The token is backend-issued and backend-stored.
  The backend decides its format, length, and
  expiry. Workpull never generates, validates, or
  stores it; it presents the token unchanged to
  the release, transition, and discard hooks,
  which act only when it matches the stored claim.
- This adapter's claim flow: the claim hook
  generates the token from the operating system's
  random source, writes the token entry into the
  ticket's per-ticket record, and returns the
  ticket and the plaintext token in its TOML
  output. That output is the token's one
  presentation. The plaintext is never stored:
  the record holds only the token's hash, per the
  storage section below.
- The release, transition, and discard hooks
  validate the presented token against the stored
  form before they act; a mismatch exits non-zero
  and changes nothing. Transition clears the
  token entry when it writes the waiting-for
  state, because the claim ends on the move.
  Discard removes the whole record, so the token
  is invalid afterwards (design 018).
- Claim changes no state. It is a lock, and the
  claim names the accountable holder of the ticket.

### Release

- The release hook checks the presented token
  against the stored claim and, only on a match,
  ends the claim. The ticket's state and priority
  do not change.

### Transition and system move

- The transition hook checks the token, then puts
  the ticket into wait for the to-state, and ends
  the claim on the move (designs 011, 015).
- The system-move hook completes a move: it takes a
  ticket out of wait for the to-state and puts it
  in work in the to-state. No claim, no token; the
  system is the mover (design 016). The pull sweep
  and the transition cascade compose count,
  list-waiting, and system-move exactly as designs
  016 and 019 specify, so the adapter adds no pull
  logic of its own.

### Count and get-state

- Count for a state returns two numbers (design
  012): `work` counts the tickets whose work state
  is that state, including a waiting ticket that
  left it; `wait` counts the tickets waiting for
  that state. A waiting ticket counts as work in
  the state it left and as wait in the state it
  waits for.
- Get-state returns, for a waiting ticket, the
  state it waits for, not the work state it left
  (design 013).

### List waiting

- The list-waiting hook returns the ids of the
  tickets waiting for the named state, sorted by
  the backend's priority order, highest first
  (design 016). Workpull pulls the first id; the
  adapter never chooses beyond the order it keeps.

### Discard

- The discard hook checks the token, then takes the
  ticket out of the system (design 018): it is in
  no state, carries no priority, counts against no
  state's WIP, and the token is invalid afterwards.
  Only the claim holder can discard, with the
  token. Discard is final; no Workpull command
  brings a discarded ticket back.

## Per-ticket record — decided: on the issue itself

Decided by Satish, 2026-11-15. The adapter keeps
three pieces of data per ticket that GitHub has
no field for:

- the priority order key (design 008),
- the claim token, while the ticket is claimed
  (design 015),
- which state the ticket waits for, while it
  waits (designs 011, 013).

All three live on the issue itself, in one
per-ticket record. The state is not in the
record: it is the `workpull:` label, per the
state model above. The record carries everything
else, in one place, so an operation that changes
per-ticket data rewrites one block and at most
one label.

- Satish's scoping: this is a choice for now. If
  Workpull really becomes popular, hosted
  solutions can be provided then, or users can
  build their own stores. That is a later concern
  if adoption warrants it, not a 0.2 design
  obligation, and this design builds no pluggable
  store abstraction for it.

### The block

- The record is a marked block in the issue body.
  It opens with the marker line
  `<!-- workpull:record:start -->` and closes with
  `<!-- workpull:record:end -->`. Between the
  markers is one fenced TOML block:

  ```toml
  key = "a0"
  waiting_for = "In Progress"
  ```

- The fields:
  - `key`: the priority order key, a string.
    Present from adopt until discard.
  - `waiting_for`: the name of the state the
    ticket waits for. Present only while the
    ticket waits.
  - `token_hash`: the claim token's one-way
    hash. Present only while the ticket is
    claimed; the stored form is decided below.
- Why the body, and not an adapter-owned comment:
  a GitHub comment can be edited only by its
  author, and the claim is a distributed lock
  (design 015), so every operator's hooks must be
  able to update the same record. A credential
  with write access to the repository can edit an
  issue body, so the body block is the record
  surface every operator shares.
- The adapter rewrites only the marked block. The
  rest of the body is the operator's own text,
  left as it is. Adopt appends the block to the
  body with the initial key; discard removes the
  block and the state label together, so a
  discarded issue carries no Workpull data.
- A missing or malformed block on an issue that
  carries a state label is a hand-edit case,
  under Satish's ruling with the labels: the
  user's own setup, on them, and no reading is
  promised for it.

### The claim token's stored form — decided: the hash

Decided by Satish, 2026-11-15: start with the
hash form; we can evolve later. The token's
stored form is `token_hash`, a one-way hash of
the token (this adapter: SHA-256, hex). The
plaintext token stays off the issue: it is shown
once, at claim time, and cannot be recovered
from the record. The hooks hash a presented
token and compare; Workpull never sees the
stored form at all. The rest of this design is
unchanged by the choice.

- A lost token is unrecoverable, and that is
  accepted for now. If the claimer loses it — an
  agent whose context is compacted or whose
  session restarts — the claim is stuck: nobody
  can release, transition, or discard the ticket,
  and clearing it takes an operator editing the
  record by hand, outside Workpull.
- The later evolution, if needed:
  `token_encrypted` — the token encrypted to the
  claim holder's public key, so the holder can
  decrypt and recover it while repository readers
  see only ciphertext. The trade: the token
  becomes recoverable by its holder, at the price
  of public-key plumbing and key management. It
  is not a 0.2 obligation.

## What it does not do

- No Workpull core change, no new command, no new
  hook. If the adapter seems to need one, that is a
  finding about the core contract, and it stops
  here rather than bending the adapter around it.
- No issue creation. Workpull does not create
  tickets, in any backend.
- No pluggable store and no hosted store. The
  on-issue record is the store for now, under
  Satish's scoping in the storage section above.
- No priority value crosses a hook boundary, and no
  hook returns issue text. Ticket ids only.
