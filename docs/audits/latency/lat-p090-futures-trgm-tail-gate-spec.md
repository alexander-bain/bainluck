# LAT-P090 — PRE-REGISTERED GATE SPEC: a tail-scoped futures trigram index

**Status: SPEC ONLY. No DDL has been run against this. The bars below are frozen
as of 2026-08-25 and are frozen BEFORE any index exists to grade.**

Written by LAT-P090 on Fable's directive of 2026-08-25 (pasted and reviewed by
Alex): *"IF you want the trigram index back for the selective tail, write a NEW
pre-registered per-term gate as a spec for a future attended batch — bar frozen
before any DDL, per the standing rule."*

---

## 0. What this is NOT

🔴 **This is not a re-grade of LAT-P088, and nothing here reopens it.**

`ix_futures_name_trgm_open` was specified by LAT-P088, built by Alex in an
attended psql batch on 2026-08-25, gated against a bar registered before the
build, and came back **RED**: median per-term collapse **0.7194** against a
**0.5** ceiling. Alex dropped it. That verdict stands, that index stays dropped,
and the process ruling that produced it — *a lane does not re-grade its own bar
after the result, and that discipline outranks any single index* — is the reason
this document exists as a fresh proposal rather than as an appeal.

The distinction that makes a new gate legitimate rather than a second bite:

|                     | LAT-P088's index          | This proposal                        |
|---------------------|---------------------------|--------------------------------------|
| Scope               | all `/search` name matching | the **selective tail only**        |
| Claim               | the endpoint gets faster  | the tail arm collapses; the head is untouched |
| Bar                 | pooled median ≤ 0.50      | partitioned, both halves bound, ≤ 0.25 / ≤ 1.25 |
| Precondition        | none                      | a **value gate** that can refuse the DDL outright |
| Head traffic        | in scope                  | **out of scope — already solved by LAT-P090's cache** |

A different index, a different claim, a different and tighter bar. If a future
window wants to argue the OLD bar was wrong, that is a separate conversation
with Alex and it is not this document.

---

## 1. The evidence this proposal rests on

LAT-P088's `after` run, `docs/audits/latency/lat-p088-futures-open-trgm-gate-after.json`.
Semantics were clean (8/8 identical id sets), the index was chosen 8/8, and no
term regressed. The RED was the budget arm alone, and the per-term table under
that median does not look like noise:

| term                    | before ratio | after ratio | collapse | reading |
|-------------------------|--------------|-------------|----------|---------|
| `super bowl`            | 0.073        | 0.057       | **0.078** | tail — index wins big |
| `world series`          | 0.891        | 0.074       | **0.083** | tail |
| `best picture`          | 0.277        | 0.368       | **0.368** | tail |
| `world cup`             | 5.486        | 2.745       | **0.500** | tail |
| `champion`              | 1.114        | 0.661       | **0.593** | boundary |
| `presidential election` | 3.149        | 2.072       | **0.658** | boundary |
| `winner`                | 0.579        | 0.567       | **0.979** | head — index does nothing |
| `election`              | 10.02        | 9.996       | **0.998** | head |

The split has a mechanical cause, not a statistical one. A trigram GIN is a
selectivity instrument. `%winner%` matches **42,336** of **858,938**
`futures_markets` rows; the bitmap it builds covers most of the table, so the
index scan costs what the sequential scan costs. **The common-word head cannot
be fixed by any string index** — a second, better-tuned index lands in the same
place. Pooling both populations under one median let the head drag a genuine
tail win over the ceiling.

**And the head no longer needs an index at all.** LAT-P090 shipped a response
cache on `GET /api/events/search` plus a warmer over the 30-day head of
`search_query_logs`. The head is now answered from Redis before the query runs.
Whatever remains for an index to win is, by construction, in the tail.

---

## 2. The partition rule — frozen, and computable before the DDL

A partitioned bar is only honest if the partition cannot be drawn after seeing
the result. Three properties are required and all three are frozen here:

1. **The rule is stated now**, in this document, before any index exists.
2. **It is computed from a pre-DDL measurement** that does not depend on the
   index — a plain `COUNT(*)` on the base table.
3. **The resulting assignment is written into the `before` artifact** and is
   immutable from that moment. The `after` run READS the assignment; it never
   recomputes it.

> **RULE.** For candidate term `t`, let
> `m(t) = SELECT count(*) FROM futures_markets WHERE name ILIKE '%t%'`
> and let `N = SELECT count(*) FROM futures_markets`.
>
> `t` is **SELECTIVE** iff `m(t) / N <= 0.02`.
> `t` is **HEAD** otherwise.
>
> The threshold is **0.02** and it does not move.

Why 0.02 rather than a number fitted to the table above: it is the point at
which a bitmap heap scan stops being most of the relation, which is the property
that decides whether a trigram index can help at all. `%winner%` sits at 0.049
and is therefore HEAD — which the measurement already agrees with (collapse
0.979), and that agreement is a check on the rule, not the source of it. The one
term whose classification this document cannot predict is `champion`
(collapse 0.593, boundary); its `m(t)` has never been measured, so it will fall
where the rule puts it. **That is deliberate. A partition rule you can fully
predict the output of is a term list wearing a rule's clothes.**

### Candidate term list — FROZEN

Extended beyond LAT-P088's eight so the SELECTIVE partition cannot be a
four-item median. Words and multi-word phrases both appear, because
`search_events()` branches its whole predicate on `len(terms) > 1`.

```
world series · super bowl · best picture · world cup · stanley cup ·
masters winner · nba champion · presidential election · champion ·
winner · election · mvp · playoffs · nobel prize
```

No term may be added or removed after the `before` run is recorded. A term whose
`m(t)` cannot be measured is **excluded and named in the artifact**, never
silently dropped (gotcha #53 — an unread term and a passing term must not arrive
in the same shape; LAT-P088's harness already reports this as
`unread in BOTH runs`).

---

## 3. THE PRECONDITION GATE — this can refuse the DDL without running it

**Run this BEFORE scheduling any attended psql batch.** Both arms must pass, or
the index is REFUSED and no DDL is scheduled.

This gate exists because LAT-P090 changed what the index is worth. An index on a
985 MB / 858,938-row table is not free: it costs disk, it costs write
amplification on every futures upsert, and — per `typeahead_warmer`'s own
measurement — index pages compete for a 1 GB `shared_buffers` that
`ix_futures_outcomes_name_trgm` (406 MB) and `ix_futures_name_trgm` (172 MB)
already want 56% of. Buying that for queries nobody types would be a real
regression dressed as a win.

**P1 — TRAFFIC.** Over the trailing 30 days of `search_query_logs`, the share of
submitted queries whose terms are ALL in the SELECTIVE partition must be
**≥ 15%** of queries not already served by the warmed head.

**P2 — HEADROOM.** In the gate's own `--label before` run, the SELECTIVE
partition's median arm cost must be **≥ 250 ms**.

> ⚠️ P2 is an absolute millisecond number and that is deliberate and narrow.
> `scripts/gate_futures_open_trgm_index.py` bans absolute constants **as the
> budget threshold**, because the lane got that wrong three times — a hardcoded
> `ratio <= 0.25` once passed `super bowl` with no index in production at all.
> P2 is not a budget threshold. It answers a different question — *is there
> anything here to win?* — and it is checked before the index exists, so it
> cannot be satisfied by the index it is deciding about.

**If P1 or P2 fails: the answer is NO INDEX, and that is a real outcome, not a
deferral.** Record it in the artifact and close the thread.

---

## 4. THE BARS — frozen 2026-08-25, before any DDL

All four must pass. `rounds = 9`, not 5: the head bar below is tight enough that
five-round medians would put flake inside the margin, and a bar that fails on
noise teaches a lane to re-run rather than to believe.

| # | arm | bar |
|---|-----|-----|
| **B1** | SEMANTICS | id sets identical `before` vs `after` for **every** term. Unread terms excluded AND named, never counted as passing. |
| **B2** | SELECTIVE — median | `median over SELECTIVE of (ratio_after / ratio_before)` **≤ 0.25** |
| **B3** | SELECTIVE — no free riders | **every** SELECTIVE term individually **≤ 0.50** |
| **B4** | HEAD — non-regression | **every** HEAD term **≤ 1.25 ×** its own recorded before-ratio |

**B2 is 0.25 and not 0.35, and the reason is not the table in §1.** The bar is
set from what the index must deliver to be worth its cost, and the cost changed
when LAT-P090 removed the head from the critical path. What is left to buy is a
tail arm that stops mattering — a 4× collapse — not a tail arm that is somewhat
cheaper. Setting the bar at the level the dropped index already cleared on these
terms (its tail median was ≈ 0.23) would be choosing a number I already know
passes, which is a ceremony, not a test. 0.25 is close enough to that value to
be a genuine coin-flip on a differently-scoped index, and it is derived from the
cost argument rather than from the observation.

**B4 is 1.25 and not LAT-P088's 1.5** because this proposal's whole claim is that
the head is UNAFFECTED. A claim of no effect must be gated more tightly than a
claim of improvement, or it is not being tested.

### What this gate must SEE to go RED

Named as inputs, per Fable's standing rule of 2026-08-19 — coverage claimed
without a failing input is not coverage:

* **A no-op index.** Every ratio lands at 1.0, B2 reads 1.0 against 0.25, RED.
  This is the LAT-P088 harness's own `noop self-test`, which measured 1.005 and
  1.295 against a 0.5 ceiling — it must be re-run against 0.25 and recorded.
* **A tail win bought with a head regression.** `election` at 1.4× its before
  ratio: B2 could pass and B4 fires. This is the failure the partition creates
  the opportunity for, and B4 exists solely to close it.
* **One free rider inside the tail.** Three terms at 0.05 and one at 0.9 give a
  median under 0.25; B3 fires. A partitioned median can hide a straggler exactly
  the way the pooled one hid the head.
* **A partition drawn after the fact.** If the `after` run recomputes `m(t)`
  instead of reading the frozen assignment out of the `before` artifact, the
  harness must **exit 2 (cannot run)**, not produce a verdict.

---

## 5. Harness delta required

`scripts/gate_futures_open_trgm_index.py` is the right shape and should not be
rewritten. The delta a future window needs, stated so it is not re-designed
under time pressure:

1. `TERMS` → the §2 frozen list.
2. New `--label before` step: measure `m(t)` and `N`, assign each term
   SELECTIVE/HEAD by the frozen 0.02 rule, and write the assignment into the
   artifact.
3. `--label after`: **read** the assignment from the `before` artifact. Refuse
   with exit 2 if it is absent. Never recompute it.
4. Replace the single `MEDIAN_COLLAPSE_FACTOR = 0.5` with `B2 = 0.25`,
   `B3 = 0.50`, `B4 = 1.25`, and report the four arms separately — a verdict
   that cannot say WHICH bar failed sends the next window back to the JSON.
5. `DEFAULT_ROUNDS` 5 → 9.
6. `tests/test_gate_futures_open_trgm_index.py` gains a case per bar, plus one
   asserting the `after` path refuses to recompute the partition.

**The DDL itself is unchanged from LAT-P088's spec** and still runs in an
attended psql batch, never in Alembic (gotcha #31 — Heroku's release phase times
out at ≈5 min and this index is minutes of build).

---

## 6. Where this is parked

This lane is not scheduling it. Under ruling 134 the measurement half (P1, P2 and
the `before` run) belongs to the measurement lane, and the DDL half belongs to an
attended batch of Alex's. Both are parked in
`.claude/handoff/PARKED-MEASUREMENTS.md` and come back when a named ship needs
them.

**And the honest prior is that P1 may well fail.** The tail is by definition the
low-volume part of the distribution, and LAT-P090 just took the high-volume part
out of the database entirely. If the measurement says the tail is 4% of traffic,
the correct outcome is no index — and this document will have done its job by
producing that answer for the price of a query instead of the price of a
985 MB build, an attended window, and a third RED.
