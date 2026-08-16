# RULING 071 — A lock file with more than one `status:` line is MALFORMED, and a malformed lock reads as HELD

date: 2026-08-15
author: Fable
context: INT-072 directive — issued after a second malformed lane lock was found in two cycles. Extends ruling 008 (validity is the owner pid being alive) and ruling 013 (an explicit RELEASED frees a lock regardless of pid), which between them leave this case undefined.

## The ruling

A lane lock file carrying **more than one `status:` line, or more than one `owner_pid:` line, is MALFORMED.**

A malformed lock **reads as HELD.** Fail-safe, not fail-open.

**Repair belongs to the OWNER** if the owner's pid is alive. If and only if the pid is `ps`-verified dead may another lane take it over, and the takeover is recorded per ruling 008.

## Why HELD is the correct default, and not a coin flip

Rulings 008 and 013 between them define the lock's state space completely — *for a well-formed file*. 008 says a live owner pid holds it; 013 says an explicit `RELEASED` frees it regardless of pid. Both are sound. But a file that says **`RELEASED` on one line and `HELD` on another, with one live pid and one dead one, satisfies the premise of both rulings at once and they return opposite answers.**

That is not a rule conflict; it is an *undefined case*. And ruling 013 already recorded what an undefined case costs: "an undefined case in a lock protocol resolves to whatever the reader guesses, and half will guess the blocking direction." The half that guess the *other* way put a second writer on master.

So the tie is broken by consequence, not by elegance:

- Guess FREE when the lane is genuinely working → **two integrators push master concurrently, invisibly to each other.** That is the 2026-08-09 named failure, and the single-writer invariant is the one thing the lock exists to protect.
- Guess HELD when the lane is genuinely idle → **one cycle is delayed**, and ruling 013's release makes the recovery immediate and cheap.

Those costs are not comparable. A malformed lock is a lock whose author lost track of its own state; the only safe reading of "I do not know" is "do not write."

## What made this necessary — it is mechanical, not sloppiness

INT-071 found `LANE-calibration.lock` carrying **12 `status:` lines and 10 `owner_pid:` lines**, the first reading `RELEASED` and a later one reading `HELD` with a live pid. INT-072's scout then found a **second** malformed lock: `LANE-lane1.lock`, 6 `status:` / 5 `owner_pid:`, its top line a six-way stamped `status: HELD   # …358.   # …357.   # …`.

The cause is not a careless window. **`claim_lane_lock.py release` appends its release stamp to the existing top `status:` line rather than writing a fresh header.** Every release compounds the line. Do this ten times and the file's own first line is an unreadable audit trail with a verdict buried somewhere inside it.

That matters for how this ruling is enforced: **the fix is to the release mechanism, not to lane discipline.** This is the same lesson as the append-helper (PROCESS-BATCH item 6) — read-then-write had been "understood" by everyone and still ate 388 KB, because what survives a long session is a mechanism, not a resolution. Ask a tired lane to remember to rewrite a header cleanly and it will comply ninety times and compound it on the ninety-first.

Note also the partial mitigation already attempted and why it is not enough: `LANE-calibration.lock` was deliberately restructured with an `## AUTHORITATIVE HEADER — this block, and only this block, decides the lock` fence above a `# ==== RETAINED HISTORY ====` section. That is a thoughtful repair, and under this ruling the file is **still malformed**, because a convention that requires the reader to know about the fence fails exactly for the reader who does not — a new window, a subagent, a `grep`. A lock's state must be legible to `grep -c '^status:'`.

## Consequences

1. **Enforce it in the lint,** alongside the READY-file multi-status rule (PROCESS-BATCH items 4-6). A lock or READY file with more than one `status:`/`owner_pid:` line fails.
2. **Fix `claim_lane_lock.py release`** to rewrite the header rather than append to it. Retained history belongs *below* the header, never inside the `status:` line.
3. **A lane that finds its own lock malformed repairs it** — that is the owner's job while it is alive, and it is one edit.
4. **A lane that finds ANOTHER lane's lock malformed does not touch it, and does not proceed into that lane's files.** INT-071 declined to write into any calibration file on exactly this basis, and INT-072 held the same line while Alex checked the window.

## The general form

This is the lock-protocol instance of a pattern the batch keeps meeting: **an instrument that reports two incompatible things at once is not partially informative, it is uninformative** — and the danger is that it *looks* informative, because every individual line in it is well-formed and plausible. Sibling of #53 (an empty 200 is a response shape, not a fact), #124 (`$?` belongs to the last thing that ran), and #49 (a lifetime count read as recent). In all four, the reader is handed a real number or a real word in exactly the place the answer belongs, and it is the wrong one.
