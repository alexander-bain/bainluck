# RULING 095 — A census of a moving population is fiction; freeze the population or prove stillness first

date: 2026-08-19
author: Fable (ratifying queue 371's stillness-gate precondition, on the q372 directive)
issues: #1981 · #1989

**Before a repair censuses a population, it must either FREEZE that population or PROVE it is
still. A census taken over rows that are actively being rewritten is not a snapshot of anything —
it is a reading of one instant, presented in a format that claims to describe a set. Stillness is
demonstrated by N ≥ 3 reads spanning > 300 s with the identity fields unchanged, and "the writer
is fixed" is not stillness until the fix is DEPLOYED.**

## Why

A census is the artifact everything downstream trusts. The plan is bound to it, the reviewer
approves against it, the apply is addressed to it, and the MC is a human's signature on it. Every
one of those steps treats the census as a description of a *set of rows*. If the rows moved while
it was being taken, none of that is true: the plan is bound to an address that no longer resolves,
the reviewer approved a state that has since been overwritten, and the apply writes a correction
computed from a row that has already been corrected — or worse, re-corrupted differently.

The failure is specifically hard to notice because a census over a moving population **succeeds**.
It returns rows. It returns a plausible count. Nothing errors. The artifact mints, the digest
computes, and the digest is stable — because a digest over fiction is a perfectly good digest. The
only way to learn the population moved is to read it twice, which is the thing a frozen census is
designed to make unnecessary.

## The charter case

Queue 371 staged the eight-flapper repair and, before censusing, re-read the population roughly
fifty minutes apart. The rows had not merely changed value — their **identity** had moved:

- `15199901` moved from commence `2026-08-18 22:40` to `2026-08-19 16:35`, status `live`, score
  **4-1** — sixteen hours before that game's first pitch.
- `15200806` showed `live` **7-1** on a game commencing `2026-08-20 17:10Z`, and was labelled with a
  team pairing different from the earlier read.
- `commence_time_source` flipped to `statpal` on eight rows.

Had the census been taken at either read, it would have produced a confident, well-formed,
digest-stable artifact describing a set of rows that did not exist at the other read. Alex would
have been asked to sign it. **The plan's central finding was therefore that the plan should not
run yet** — which is the correct output of a repair design, and is only reachable by reading twice.

## What makes this different from ordinary staleness

Ordinary staleness is a value drifting under a snapshot, and it is usually tolerable: the repair
recomputes, or the write is a compare-and-set that refuses. This is not that. Here the **identity**
moved — the commence_time, the status, and in one case the team pairing. Identity is what an
address is built from. When identity moves:

- a plan bound by `(sport, commence_time, teams)` addresses a different row than it described;
- a per-row compare-and-set does not save you, because the CAS predicate was also derived from the
  moved fields, so it can *match* the wrong row;
- and the repair's own verification query re-derives the same moved address, so it reports success.

This is why the requirement is stillness and not merely freshness. A fresh read of a moving row is
still a reading of one instant.

## The obligations

1. **Freeze or prove.** Either take an exclusive hold on the population for the duration (rarely
   available here), or demonstrate stillness: **N ≥ 3 reads spanning > 300 s**, identity fields
   byte-identical across all of them. Fewer reads or a shorter span is not a weaker proof, it is
   not a proof — two adjacent reads inside one write interval agree by construction.
2. **Name the writers, and require them DEAD, not fixed.** A merged fix is not a stopped writer; a
   deployed fix is. Queue 371's flapper population had two writers, and the repair plan gates on
   both being deployed. `#1984 is open` and `#1984 is deployed` are different sentences and only
   the second one licenses a census.
3. **A stillness read is evidence and is recorded** — the timestamps, the span, the fields
   compared. "We checked" is not the artifact; the three reads are.
4. **A census that cannot prove stillness produces a REFUSAL, not a smaller census.** Narrowing the
   population to the rows that happened to hold still across two reads selects for rows between
   writes, which is the worst possible sample: it is biased precisely toward looking calm.

## Relationship to the neighbouring rulings

Ruling 048 is about not absorbing on evidence that cannot discriminate; this is the same instinct
applied to the *reading* side rather than the writing side. Gotcha #53's shape recurs once more: a
census that returns rows cannot, by itself, distinguish "here is the population" from "here is what
the population looked like during one write cycle" — and as always the fix is not to reason harder
about the single reading, it is to obtain a second signal. Here the second signal is time.

And the reason this is worth a ruling rather than a note: **the moving population in the charter
case was moving because of a defect the same programme was in the middle of fixing** (#1989's
absorber and #1981's scores writer, one mechanism at two ends). That will be the common case. The
rows a repair wants to census are, almost by definition, rows something is still writing wrongly —
so "prove stillness first" is not a rare precaution, it is the default order of operations.
