# RULING 005 — Extract-on-touch

date: 2026-08-09
author: Alex
via: Fable, from the over-engineering audit
issues: #1545 · #1546

**DO NOT REMOVE (CI-guarded).**

> **No standalone refactor queues** for `events.py`, `feed.py`, `precompute_calibration.py`,
> `golf.py`. When a defect fix lands in one of them, **the policy it touched is extracted as a
> pure module WITH the fix.** First customer: the golf membership P1.
>
> Same for the cache envelope: it is **the contract for any cache tier being touched**, never a
> bulk migration.

## Why refactor-first is refused here

A standalone refactor of a hot file is a large diff with **no visible outcome**, landing in the
file most likely to be edited by another lane, and it competes with defect work for the same
review attention. It is also the diff most likely to be deferred forever, which means the
cleanliness is never actually bought.

Extract-on-touch pays for the same cleanup out of a budget that already exists. The defect fix
justifies opening the file; the extraction rides along; the pure module arrives with tests
already written for the bug. The blast radius is bounded to the policy actually being changed.

## What makes it verifiable rather than aspirational

The extracted unit must be a **pure module** — no ORM session, no request context — so it is
testable without fixtures, which is the property that makes the next fix in that area cheap.
"Moved the code" without that property does not discharge the ruling.

The cache-envelope clause is the same shape one level up. A bulk cache migration is a refactor
queue wearing different clothes: broad, invisible, and risky in exactly the tiers that are hard
to test. Applying the envelope as the contract *for the tier you are already in* gets the same
convergence with a revert boundary at every step.

**The reason to write it down** is that both of these read as prudent engineering when proposed.
The ruling is not that the cleanup is wrong; it is that the cleanup does not get its own queue.

## The cache envelope contract

Written out as a one-page spec at **`docs/contracts/cache-envelope.md`**: five fields —
`generation`, `created_at`, `quality`, `availability`, `lifecycle_watermark` — with the rules
that make them load-bearing rather than decorative. Apply it to the tier you are already in.

First customers, in likely order of being touched: the `/api/event/{key}` concept cache (#1107,
where Codex C224 found a 24h fallback with no age or status disclosure — three of these five
fields simply absent), then the calibration durable copy, which already publishes `cache.status`
and `cache.reason` and is the closest thing to a working prototype.
