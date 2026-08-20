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

---

## AMENDMENT — 2026-08-20 (Alex, RULINGS-NEEDED item 12; queue 385)

### The bounding clause was measured, and it is currently worth nothing

This ruling's cost model rests on one sentence:

> *"Id-keyed reconciliation drains the duplicate when an id arrives."*

That clause is the whole reason "duplicates go up" reads as a **bounded** price rather than an
unbounded one. Queue 384 measured what it is worth across the **whole** unanchored population
(`db-query`, 2026-08-20T19:36Z — an earlier "~96%" reading was a 2,000-row sample and understated
it):

| disposition | rows | share |
|---|---:|---:|
| `NO_ANCHOR_CHANNEL` — the creating provider has **no id column on `events`** | **74,181** | **99.61%** |
| anchored — an id did arrive | 292 | 0.39% |
| **`AWAITING_ANCHOR` — an id may yet arrive** | **0** | **0.00%** |

**`AWAITING_ANCHOR` is exactly zero.** Not small — zero. There is not one row in the entire
unanchored population for which the arrival this ruling waits on is even *possible*. The
composition is `kalshi` **73,678** and `polymarket` **503**, and `events` carries exactly three
provider-id columns (`external_id`/odds_api, `espn_id`/espn, `statpal_fixture_id`/statpal).
Neither Kalshi nor Polymarket has one.

So the bound is not lagging, or under-resourced, or waiting on a scheduler. It is **structurally
unreachable** for 99.61% of the population it bills. A deferred drain and a drain that can never
run produce the same number today and opposite futures — which is gotcha #53 wearing a different
hat, and it is why this was escalated rather than settled in-lane.

### The ruling: OPTION A — build the channel

Alex, 2026-08-20. **The bargain stands; the missing half gets built.**
`event_provider_anchors` ships per `docs/event-provider-anchor-channel-1946.md`, **redesigned
Kalshi-first** on queue 384's composition measurement: Kalshi is 99.3% of the population, one game
maps to many tickers, and Polymarket's `condition_id` nesting is the second case, not the first.
`id_kind='game'` remains load-bearing — a prop ticker records the anchor but never asserts game
identity.

**Option C — loosen absorption back toward name-and-time because the duplicates are expensive —
is REJECTED EXPLICITLY.** We do not trade visible duplicates for invisible missing rows. That is
this ruling's own asymmetry argument, and the measurement does not weaken it: it says the
*mitigation* was never built, not that the *choice* was wrong. A duplicate is still visible and
reversible; a wrong absorption is still neither.

### What is true until the table ships

**The bounding clause is unexecutable prose, and this file says so rather than implying otherwise.**
Anyone citing "reconciliation drains the duplicate" as a live guarantee before
`event_provider_anchors` exists is citing an intention. Until then:

- the duplicate cost is **declared and REAL**, not declared and bounded;
- a row whose creating provider has no anchor channel must be reported
  `NO_ANCHOR_CHANNEL`, **never** `AWAITING_ANCHOR` — the two say opposite things to an operator;
- and the acceptance box above ("the post-deploy duplicate creation rate is MEASURED and
  reported") is *more* load-bearing, not less, because the drain rate it was to be reported
  against is currently structurally zero.

The §4 replacement text for the bounding clause is already drafted in the design doc and takes
effect **when the channel ships**, not now. Staged as queue 386 with a migration-slot request.
