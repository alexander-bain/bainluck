# RULING 116 — Gotcha numbers claim through `RULING-CLAIMS.md`, and collisions renumber at merge by COUNTING the merged tree

date: 2026-08-21
author: Fable (banked by the Integrator, INT-105, at Fable's instruction)
issues: #1621
supersedes nothing; **re-ratifies and completes** the 2026-08-12 scope clause

## The ruling

**Gotcha numbers claim through `.claude/handoff/RULING-CLAIMS.md` exactly like ruling numbers and
doctrine-clause numbers.** No lane writes `NNN.` into `docs/gotchas-reference.md` without first
claiming `NNN` in the ledger, against a `git fetch` in the same turn.

**And when two lanes arrive at the Integrator holding the same gotcha number, the Integrator
renumbers at merge BY THE LEDGER, COUNTING THE MERGED TREE.** Not by seniority, not by taking a
side, not by adding a delta to either branch's number. The ledger says who claimed what and when;
the merged tree says what numbers are actually occupied. The resolution is the intersection.

## Why this needed saying again

**The scope clause already existed.** Alex ruled on 2026-08-12, on the UX-P066 acceptance, that
the ledger covers *"every monotonic doc number in the repo"* — rulings, gotchas, and (from
2026-08-19) doctrine clauses. `RULING-CLAIMS.md` has carried a `## GOTCHAS` section ever since,
with an explicit `NEXT FREE IS …` line and a claims table.

Before this cycle it had not been used for a gotcha since **2026-08-18** (the last table claim is
139) — and the one claim this cycle did produce arrived *after* the entry was already written.

Charter case, measured: on **2026-08-21**, master's highest gotcha was **144**, and **three lanes
arrived at INT-105 holding four new gotchas between them, competing for two numbers**:

| lane | claimed | title |
|---|---|---|
| `lane1/q387-meter-split` (PR #2070) | **145** | a copied-forward sentence is not a measurement |
| `program/latency-72` (LAT-P079) | **146** | a saturated statistic is not a failing task |
| `program/ux-101` (UX-P114) | **145** *and* **146** | a shared constant is not a shared defect · widening a signature silently rebinds every point-free reference |

### The defect is claim ORDER, and it is sharper than "nobody claimed"

`program/latency-72` **did** claim 146 in the ledger. Its own row says how:
*"claimed **LATE** (banked before claiming)"*. `lane1/q387-meter-split` and `program/ux-101` left
no row at all.

**A claim entered after the entry is written cannot prevent a collision; it can only document
one.** That is the whole rule. The ledger is not a registry you update when convenient — its only
power is that it is consulted and written *before* the number goes into the file, and a late claim
converts it from a lock into a diary.

Each lane measured master correctly, and each was right about master. None could see the other
two. LAT-P079 did the most work of the three — it swept **538 local and remote refs** and reported
`holders_found = 0` for 146 — and it was still wrong, because `program/ux-101` held 146 and had not
pushed. **A ref sweep measures what has been PUSHED; a ledger records what has been DECIDED.** The
two answer different questions, and with three lanes writing simultaneously only the second helps.

### ✅ What worked, recorded because it is the model

The latency lane, having lost a number to this, then wrote the full 2×2 collision into the ledger
**as a service to INT-105** — every holder, every entry, and the author timestamps — explicitly
flagging itself as *"a party to this collision, not its referee"* and marking its recommendation
advisory. It reached the same resolution this cycle applied (lane1 keeps 145, latency keeps 146,
ux-101 renumbers) by a **different discriminator**: banking order, where the Integrator used
cross-reference minimisation.

Two independent routes to one answer is the strongest form this kind of adjudication gets, and it
happened because a lane wrote down what it knew in the shared place instead of only in its own
report. That behaviour is the ruling working even before the ruling existed.

## The mechanic, so it is not re-derived each time

`docs/gotchas-reference.md` is still ONE shared append region — rulings got per-file treatment in
ruling 001 and gotchas never did, which is a known structural hazard the ledger itself records.
So every simultaneous claim is BOTH a number collision and a textual conflict, and the Integrator
resolves them together:

1. **Keep every entry.** A gotcha is evidence; none is dropped because its number was taken.
2. **The earlier ledger claim keeps its number.** A LATE claim — entered after the entry was
   written — is not void, but it does not outrank an earlier one. Where no lane claimed in time,
   fall back to banking order, then to merge order.
3. **The later claimant renumbers ITS OWN entries upward**, into the next free numbers **counted
   in the merged tree**. Never renumber the other lane's, and never renumber into a historical
   gap: a gap is not a slot (ruling 088).
4. **Prefer the order that minimises cross-reference breakage.** Check which branches reference
   their own numbers elsewhere in code and docs before choosing who renumbers; in the charter case
   #2070 and latency-72 each had two self-references and ux-101 had none, so ux-101 moved and
   **nothing else in the tree had to change**.
5. **Then count.** `grep -oE '^[0-9]{3}\. \*\*' docs/gotchas-reference.md` over the MERGED tree,
   assert no duplicates, and record the result in the ledger.

Charter-case outcome: 145 (#2070) · 146 (latency-72) · **147, 148** (ux-101, renumbered) — four
gotchas preserved, zero duplicates, zero cross-references touched.

## The general clause

**A number is not free because your measurement says so; it is free because nobody has claimed
it.** Measurement answers a question about the past — what has already been written down and
pushed. Concurrency is a question about the present: who is writing right now, in a tree you
cannot see. A ledger is the only instrument that answers the second question, which is why
skipping it is invisible until exactly the moment it is expensive.

This is ruling 088's *count, never author* applied one level out. 088 says a floor constant is
counted from the tree rather than written by hand. This says the same about the tree itself when
several lanes are writing into it at once: **count the merged tree, because it is the first tree in
which the answer exists.** Neither branch's number is right, and the merged one is nobody's — the
sixteenth consecutive instance of that pattern, and now the second series it governs.

Sibling of ruling **001** (which removed this failure for rulings by giving each its own file) and
of **113** / **115** (a check that lives in prose is forgotten, so it is computed in the tool's own
output). The real fix for gotchas is the 001 treatment — one file per gotcha — and it is still not
staged. Until it is, this ruling is what stands between four good entries and a silent renumber.
