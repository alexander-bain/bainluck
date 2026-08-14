# RULING 053 — A premise-waiting item is RE-ANCHORED at every run start

date: 2026-08-14
author: Alex
issues: #1801, #1501

A queue item whose bound names something that **did not exist when the item was written** — a
branch, a head SHA, a PR, an artifact — is not scheduling metadata. It is a **liveness claim with a
timestamp on it**, and it decays.

So at **every run start**, before eligibility is computed, each premise-waiting item's premise is
re-checked **against the world** — `git fetch`, then ask whether the named thing exists *now* — and
exactly one of two things happens:

- **ANCHOR** — rewrite the bound with the concrete SHA / PR / CI run, plus a content manifest
  specific enough that a mismatch is *detectable* rather than assumed, and drain it normally; or
- **REPORT** — state "premise still unmet at `<time>`, checked by `<command>`" as a finding in the
  run report.

Never a third thing. **Never trust the header, and never silently no-op on one.**

## The specimen — 114 seconds

`C-CERT-1801-R5` was appended to `CODEX-QUEUE.md` at **10:04 PT** on 2026-08-14. Its bound read:

> *"the implementation branch does not exist yet… if there is no implementation head, report that
> and stop."*

That sentence was **true when written and false 114 seconds later**, when `f23cd218` was pushed as
`lane1/q352` / PR #1864.

Now read what would have happened. Codex drains the item some hours later. It checks the bound,
finds the instruction to stop, and stops. It files a report saying so. **Every step of that is
correct.** The run is green. Nothing errors, nothing is flagged, no gate goes red — and the two
oldest holds in the fleet, **339T item 4 at eight windows and 341 items 1/2/3 at five**, go on
waiting for a verdict that nobody was ever going to attempt.

## WHY — a no-op and a not-applicable render identically

This is **gotcha #53 with a calendar attached.** That gotcha's subject is an API returning HTTP 200
with an empty list for both "this was purged" and "there is nothing to report", so any code that
infers a *fact* from the emptier reading invents it. Here the empty response is a **correct
stop-and-report**, and the two readings it collapses are:

| what the report says | what it could mean |
|---|---|
| "no implementation head — stopped" | the work genuinely has not been done yet |
| "no implementation head — stopped" | the work has been on a branch for hours and the header is stale |

A reader cannot tell these apart, and will supply the first one, because the first one is what a
correct-looking green run implies. The failure is not that the gate was wrong. **The failure is
that the gate could not fire and did not say so** — and a gate whose silence is indistinguishable
from its pass is not a gate.

Note also which way the damage points. An un-anchored bound never produces a *false BLOCK*, which
would be noticed within the hour. It produces a **false no-op**, which is noticed by nobody, and
whose cost is paid entirely by whatever is held behind it. That is why this rule sits at the run
start rather than in the write-side checklist: the write-side check runs once, and the item outlives
it.

## What it does NOT mean

It does not make premise-waiting items illegal. Staging work against a head that does not exist yet
is often exactly right — it is how a certification gets queued before its target is built.

It does not mean the writer is off the hook either: **liveness-check the queue at write**, as
always. But the write-side check is a *courtesy* and the run-start check is the *guarantee*, for the
one reason that decides it — **only the latter runs again.**

## The rule

> A premise is a claim about the world at a moment. Re-read the world, not the claim — and if the
> premise is still unmet, say so out loud, because a gate that cannot fire must never be allowed to
> look like a gate that passed.
