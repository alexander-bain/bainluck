# RULING 048 — An id-less claim never absorbs; it creates

date: 2026-08-14
author: Fable, ending the #1801 patch cycle after five codex blocks
via: five certification rounds that each walked a different corner of the same space and each found a new hole
issues: #1801 · #1779 · #1798 · #1814
amends: the absorption behaviour of the event-registry structured match (CLAUDE.md gotcha #32's step 3)
related: [[042-dereference-the-id-never-the-label]]

> **An id-less claim NEVER absorbs into an existing event — no time window, no name match, no
> heuristic. Absorption requires at least one shared or confirming provider id. Everything else
> CREATES, with the claim's provenance recorded, and id-keyed reconciliation drains the duplicates
> when ids later arrive.**

This changes **DESIGN, not thresholds.** That distinction is the ruling. Five rounds of tightening
the window, the name normalizer, and the tie-break were five rounds of moving a threshold inside a
design that cannot be made safe.

## The argument — the asymmetry ruling taken to its terminus

For two **distinct** games inside the same window, between the same clubs, with no provider id in
common, **there is no discriminating signal.** Not a weak one. None. The information required to
tell them apart is precisely the information an id-less claim does not carry.

It follows immediately, and it is worth stating in the sharpest form:

> **Any matcher smart enough to join two same-game claims is provably dumb enough to destroy a
> doubleheader.** They are the same operation on the same inputs. Improving one improves the other.

That is why every round produced a new specimen class rather than converging. Codex's five
certifications did not find five bugs; they walked five corners of one space, and the space has no
safe interior. A patch cycle that keeps finding new corners is reporting the shape of the space,
not the quality of the patches.

## What replaces it

1. **Absorption requires an id.** At least one shared or confirming provider id between the claim
   and the candidate event. No id, no absorption — regardless of how close the times are or how
   exactly the names match.
2. **Everything else creates**, and records the claim's **provenance** on the row it creates. A
   created row that says where it came from is a repairable fact; a wrongly-absorbed row is
   destroyed data.
3. **Id-keyed reconciliation drains the duplicates.** The merge task already exists for exactly
   this: when a later poll supplies the id that was missing, the duplicate collapses into its
   sibling. Reconciliation is deferred, not skipped.

## The cost, declared

**Duplicates go up.** That is not a regression to be quietly absorbed later — it is **the declared,
bounded price of never eating a real game**, and it is bounded because reconciliation drains it as
ids arrive.

The asymmetry that makes the trade obvious: a duplicate is **visible and reversible** — it shows up
in a count, and the merge task removes it. A wrong absorption is **invisible and irreversible** —
two games' data have already been blended onto one row, and the second game's scores, markets, and
grades are simply gone. #1779 and #1798 are what that looks like from the outside: correct team
names on rows pointing at another club, 5,142 / 540 / 2,097 rows deep.

**Prefer the failure you can see and undo.**

## Acceptance

- [ ] Codex's five specimen classes pass **BY CONSTRUCTION** — there is no id-less absorption path
      left to test. This is the tell that the change was design and not threshold: the tests become
      unreachable rather than passing.
- [ ] The `ingest_fallback` provenance path **creates cleanly**, with provenance recorded on the
      new row.
- [ ] The post-deploy **duplicate creation rate is MEASURED and reported** — not assumed bounded.
      Duplicates are now a declared cost, and a declared cost that nobody measures is just a
      regression with a good story. Report the rate and the reconciliation drain rate together;
      the second is what makes the first bounded.

## Process note

`C-CERT-1801-R5` is appended with the new head when it exists; its scope note is already with
codex. The merge gate for #1801 remains a **verdict**, not an artifact — R5 returning GREEN, not
R5 existing (Alex's general form, 2026-08-13). Two chain rows are held behind that gate: **341**
items 1/2/3 and **339T** item 4, both of which backfill data that would re-absorb if they ran
before the fix is live.
