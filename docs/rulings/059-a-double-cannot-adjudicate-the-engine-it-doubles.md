# RULING 059 — A double cannot adjudicate the engine it doubles

date: 2026-08-14
author: Fable
issues: #1586, #1544

Codex blocked the Kalshi capture SLI three times over one question — does this
row carry settlement evidence — and the third block (C-RV-7) was not a wrong
predicate. It was a **test double answering a question only the real engine can
answer**, which is why the suite was green while the defect shipped.

## What happened

The specimens executed the production `WHERE` fragments against an in-memory
SQLite with `btrim` registered as `lambda s: s.strip()`.

PostgreSQL's one-argument `btrim` removes **U+0020 and nothing else** — "a space
by default". Python's argument-less `.strip()` removes tab, newline, carriage
return, vertical tab, form feed, NBSP and the rest of Unicode whitespace. So the
fake implemented **the oracle, not the engine**, and the one test written to
catch an oracle/SQL disagreement had Python on both sides of it. A
`resolution_source` of `E'\t'` was RATED by the shipping SQL and called absent by
the classifier — the previous block's defect, recreated at a different whitespace
value, *inside the change written to prevent it*.

The demonstration is better than the argument. When the fix generated a
PostgreSQL `E''` character-class literal, the SQLite harness **could not parse the
shipping string at all**: 14 tests died on `OperationalError: syntax error`. A
double that cannot express the production predicate was never certifying it.

## The rule

> **When a test's claim is about the ENGINE's semantics — string functions,
> collation, NULL and three-valued logic, numeric and date coercion, constraint
> enforcement, index-dependent ordering — it runs against the real engine or it
> is not made. A double may stand in for the engine's PRESENCE; it may never
> adjudicate its BEHAVIOUR. And a repository with a real-Postgres CI rail has no
> excuse: the answer to a fidelity block is to move the specimen, not to raise
> the fake's fidelity.**

Raising fidelity is the trap. Every increment makes the fake more convincing and
none of them make it authoritative — you are hand-porting a semantics you do not
own, and the next character, collation or coercion rule you have not thought of
is the next block. This is the double-fidelity census's lesson wearing
calibration clothes.

## Two corollaries the specimens paid for

**A generated contract, not a transcribed one.** Where SQL and application code
must agree on a literal set — characters, names, enum values — one of them is
GENERATED from the other. Two hand-typed spellings that match today are the same
two-derivation failure waiting for an edit.

**A double is permissive in directions the schema is not.** The same SQLite
harness built its own untyped `fm(status TEXT)`, so it accepted a NULL
`futures_markets.status` — a column that is `NOT NULL` and inner-joined at every
call site. The suite therefore asserted a cell for a row the database will not
store, which reads exactly like coverage. **A specimen the schema forbids is not
coverage; the honest form of that claim is the constraint itself.**

## And the gate has to be wired

A real-engine suite that no CI job invokes never runs, and pytest exits 0 when
everything skips — so its absence is indistinguishable from its success. Wiring
it into a job is part of the move, and the wiring itself gets a test.
