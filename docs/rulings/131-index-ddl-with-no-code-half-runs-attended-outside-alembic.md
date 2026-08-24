# RULING 131 — Index DDL with no code half runs attended, outside Alembic

date: 2026-08-24
author: Fable (LAT-P086 item 0b, pasted and reviewed by Alex)
issues: #2107, #1494
supersedes:

Issued on the three `teams` FTS expression indexes proposed by the LAT-P085
search decomposition (`docs/audits/latency/lat-p085-search-decomposition.md`).

---

## The clause

**An index whose benefit requires no application change does not belong in the
migration chain. It is DDL, not a schema contract, and it runs as an attended
`psql` session against production with a named operator watching it — built
with `CREATE INDEX CONCURRENTLY`, preceded by its preconditions, followed by
its verification query, and rolled back with `DROP INDEX CONCURRENTLY`.**

Gotcha #31 already forbids `CONCURRENTLY` inside Alembic: Heroku's release
phase times out at ~5 minutes and a hung build is a full outage (the May 22
`odds_snapshots` incident). This ruling says the rest of it — that the
alternative is not "put it in Alembic without CONCURRENTLY", which trades a
timeout for an `ACCESS EXCLUSIVE` lock on a live table, but **take it out of
the release path entirely.**

The general form: **couple a change to the deploy only when the deploy is what
makes it correct.** An index that helps the query text already running in
production has no such coupling. Binding it to a release buys nothing and
inherits the release's timeout, its lock behaviour, its irreversibility, and
its unattendedness.

---

## Why the teams indexes qualify, precisely

The three GINs serve `to_tsvector(...) @@ websearch_to_tsquery(...)` arms the
`/api/events/search` route **already emits, unmodified**. There is no branch, no
flag, no query rewrite. The planner either picks a BitmapOr over the new
indexes or it does not, and the result set is provably identical either way —
which is also why the spec chose three separate indexes over one concatenated
`setweight` vector: a combined vector would let `'red' & 'sox'` match across
columns and widen recall. Same predicate, same rows, new access path.

That gives the lever an unusual property worth naming, because it is the test
this clause turns on: **there is no code revert to coordinate.** Rollback is one
`DROP INDEX CONCURRENTLY`, instant, at any hour, with nothing to redeploy.

Contrast with the LAT-P058 golf indexes, which sat behind the same reasoning
until the `IMMUTABLE` fallback appeared: that fallback's predicate did *not*
match the query's `ILIKE`, so taking it would have required a matching code
change — at which point the DDL acquires a code half and this clause stops
applying to it. The spec correctly said "stop there without flipping the flag;
do not improvise the code side."

---

## What attended means, and why it is a requirement rather than a preference

Not "run by a human instead of a script" — **run by a human who is watching the
specific things that break a `CONCURRENTLY` build and can stop.**

1. `CREATE INDEX CONCURRENTLY` **waits, twice, for every transaction that can
   see the table.** One long-running query stalls the whole build indefinitely.
   Unattended, that is indistinguishable from a slow build.
2. A failed `CONCURRENTLY` build leaves an **INVALID** index behind
   (`indisvalid = false`) that is never used by the planner but *is* maintained
   on every write. It costs and returns nothing, silently, forever. It must be
   dropped, and something has to notice it exists.
3. `statement_timeout` must be 0 and `lock_timeout` non-trivial for the
   session. LAT-P058's execution record found `lock_timeout = '5s'` FAILS in
   this database. Session GUCs are exactly the thing a migration runner does
   not give you control of.

None of those three is a property of the index. All three are properties of
building one online, and all three want an operator.

---

## What it binds

- The proposing lane writes the **exact copy-paste block**: session GUCs,
  preconditions with their abort conditions, the DDL, and a **post-create
  verification query** — in that order, in one fenced block, in the report.
- The verification query is not optional and is not "did it error". It must
  read `indisvalid` from the catalog and it must confirm the planner *uses* the
  index on a real specimen, because a valid index the planner declines is the
  same non-event as no index (gotcha #53: an empty 200 is not an absence).
- `migration_slot: none` is stated explicitly in the report either way, so
  "there is no migration" is a declaration rather than an omission.
- Until the DDL has run, the pre-registered red **stays red and stays
  pre-registered**. A lane does not get to mark a lever done because it wrote
  the command for it.

---

## What it does not bind

Schema changes — new columns, constraints, types, anything the application code
depends on the shape of — stay in Alembic, unconditionally. This clause is about
performance DDL whose absence is a slowdown rather than a break. If removing the
object would make a deployed query *wrong* rather than *slow*, it has a code
half and it is not covered here.
