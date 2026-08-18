# LAT-P063 §D — Option D: the mechanism, and the ruling-050 prediction, both registered BEFORE the work

**Written:** 2026-08-17 PDT, latency lane cycle 35, `pid:12080`, against deployed `29639b78` (v3830).
**Status of the work itself:** **NOT BUILT THIS WINDOW — and deliberately not half-built.** See §D5.
**All sizing below is MEASURED TODAY, not carried forward** (ruling 069: re-measure a bar, never
re-quote it). The numbers moved since the census, and one moved enough to matter.

---

## §D1 — The mechanism, stated so it can be wrong

Three measurements, in the order they were taken, each one closing a door:

**1. Read bandwidth is not the binding constraint.** LAT-P062 built the golf identity index, cut
DB-wide physical reads **79.1 → 34.50 MB/s** (a **56 %** cut against a predicted 21 %), took the
golf query from **516.7 → 2.629 MB/call** and from **19 %** of all physical reads to **0.105 %** —
and the typeahead tail **did not improve**. Bootstrap 95 % CI **[+25.9 %, +111.7 %]**; **0.00 %** of
resamples reached the 30 % that would have halted. **Freeing 44.6 MB/s moved the tail not at all.**
That is the strongest possible form of this result: the prediction said a read-volume cut would not
fix the tail, and it survived a cut **2.7× larger** than the one it was built on.

**2. The constraint is RESIDENCY, and the pool cannot hold what typeahead reads.** Measured today:

| trigram index | size |
|---|---|
| `ix_futures_outcomes_name_trgm` | **411 MB** |
| `ix_futures_name_trgm` | **173 MB** |
| `ix_events_away_team_name_trgm` / `ix_events_away_trgm` / `ix_events_home_trgm` / `ix_events_home_team_name_trgm` | 26 + 26 + 25 + 25 MB |
| `ix_teams_name_trgm` | 2.3 MB |
| **total typeahead trigram surface** | **688.6 MB** |

Against a **1 GiB** `shared_buffers` that also serves every other query in the product, that is
**67.2 % of the pool** — and it has **grown** since LAT-P057's census (the two futures indexes alone
are 584 MB today against 578 MB then). `pg_statio_all_indexes` put those two at a **76.5 %** hit
rate, re-reading **170.9 MB in under three minutes** (LAT-P061). A working set that large is not made
resident by other queries reading less; it is evicted by everything, continuously.

**3. The warmer is a workaround, and this window priced what the workaround costs.** At W=4 it holds
the database **73 % of wall-clock — 2.9 backend-equivalents against a ~3-backend production
baseline.** This window's forced-rebuild sweep (§W) shows W=4 buys essentially **zero** wall over W=2
while doing **twice** the database work. And even at its best the warmer reaches only **23 of 24**
head slots, and **4 of 24** during a stall (§1). **We are paying a second production workload to hold
the head of a structure that should not need holding, and it still cannot hold the tail at all —
because the tail is by definition the queries no head contains.**

**Option D changes the regime rather than the constant.** One narrow table — `entity_id`,
`entity_type`, `display_text`, `search_text`, a few rank hints — one row per searchable entity.
Re-sized today: teams **9,128** + open futures markets **51,624** + open-market outcomes (a few
hundred thousand) + recent events **21,968** + concepts ≈ **~380 k rows**. At ~120 B/row ≈ **46 MB**
heap; a trigram GIN scaled from the measured 173 MB / 783,858 rows ≈ **~90 MB**. **Total ~140 MB
against today's 688.6 MB — a 4.9× reduction.** A 140 MB working set touched on every keystroke is one
the clock-sweep **keeps**, because it is small and constantly re-referenced. That is the whole
mechanism: not fewer reads, but a working set that fits.

## §D2 — REGISTERED PREDICTION (ruling 050)

Graded next window, against these bars, not against bars written afterwards.

| # | prediction | HALT |
|---|---|---|
| **D1** | typeahead tail p50 **collapses toward `/search`-like numbers**: from ~1,800 ms to **< 700 ms** (a > 60 % improvement), measured on the same 8-query never-warmed disjoint arm, paired, ≥ 2 runs on a settled pool | **< 30 % improvement HALTS, and the table does not ship.** Residency would then not be the binding constraint either, the decomposition re-opens, and the next window must say **which** model it believes — the same obligation LAT-P058's row carried |
| **D2** | **0 of 46** gold dispositions change; `entity_top_1_rate` **0.9130434782608695** and MRR **0.9347826086956522** hold exactly | **ANY movement HALTS.** A recall change means the table is not equivalent to the thing it replaced, and an inequivalent index is a correctness bug wearing a latency fix's clothes |
| **D3** | the table + its GIN measure **< 200 MB** total, verified by `pg_relation_size` after the build | **> 350 MB** ⇒ the sizing model is wrong and the residency argument weakens in proportion. Re-derive before building the read path — do not proceed on "it is still smaller than 688" |
| **D4** | the staleness sentinel reports **drift = 0** on a settled pool within one reconcile period, and **detects an injected drift** in a test | **any nonzero steady-state drift, or an undetected injected drift, HALTS the read path.** A denormalised index that silently goes stale is a worse defect than a slow query |

**D4 is not a follow-up and not a nice-to-have.** #1866's entire history is instruments that reported
success while doing nothing — a trade backfill that recorded SUCCESS every 6 h for ten weeks while
recovering nothing (gotcha #53), a warmer whose `fresh` skip could never fire, two tests that passed
while asserting a model production had refuted. **A second copy of truth with no sentinel is the next
entry in that list.** The sentinel ships **with** the table or the table does not ship.

## §D3 — The ruling-076 tension, named rather than dodged

Option D needs a read-path switch during its grading window, and ruling 076 was banked **this week**
against exactly that shape. The distinction is real and I am stating it so nobody has to reconstruct it:

**076 forbids leaving a MEASURED-WORSE path behind a permanently-off flag.** The `UNION` was known
slower, unreachable, green-tested and documented as pending — a trap. Option D's switch gates an
**unmeasured-new** path during a **dated** grading window, with the prediction registered above and a
**deletion obligation attached in advance**: whichever arm loses, that arm is **deleted in the window
the measurement lands** — the old trigram indexes if D1 passes, the new table if D1 halts. Not parked.
Not "left off for rollback". Deleted. A rollout flag with a dated death is a rollout; one without is
the trap 076 named, and the only difference is whether the deletion is scheduled before the
measurement or negotiated after it.

## §D4 — Explicitly out of scope for Option D's queue

- **Deleting the existing trigram indexes.** That happens only after D1 passes, in a separate step,
  and it is a `DROP INDEX CONCURRENTLY` on a one-off dyno — never a migration (gotcha #31).
- **Head composition or size.** Still BLOCKED on #1916.
- **The golf route's phase 2** (45 markets / 4,621 outcomes, 99–172 KB). Real, measured, not index
  work, its own queue.
- **The warmer.** If D1 passes, the warmer's justification largely evaporates and removing it is a
  *consequence* to be measured, not an assumption to build in.

## §D5 — Why this window registered Option D instead of building it, stated plainly

**A migration slot was never assigned.** `PROGRAM-LATENCY-NEXT.md` says `migration_slot: none —
UNLESS you take Item 2, which REQUIRES one. Ask at staging.` The FABLE DIRECTIVE promoted Option D but
did not assign a slot, and PROGRAM-LANES invariant 5 is unconditional: **no slot, no migration.** I am
not going to take an unassigned slot on my own authority — two lanes creating migrations in the same
cycle is the one thing the invariant exists to prevent, and a second Alembic head is a release-phase
outage, not a merge conflict.

The second reason is the queue's own instruction, and it is the honest one: *"Stage it as its own
queue if it will not fit beside Item 0. **Do not half-take it.**"* Item 0 turned out to be a
substantial grade — four probe runs, 20 sampled passes, a natural experiment across two outages, and
two corrections I had to catch mid-flight — and the W-sweep needed **two** attempts because the first
was confounded (§W). Option D is a new table, a builder, a reconcile path, a sentinel, a read path and
a recall proof. Building half of it and leaving a table nothing writes to would be worse than
building none of it.

**What Option D's queue needs at staging, so the next window is not blocked the same way:**

1. **A migration slot** for `CREATE TABLE` + its small btrees (instant, safe in Alembic).
2. **An explicit note that the ~90 MB trigram GIN is NOT in the migration** — it is a
   `CREATE INDEX CONCURRENTLY` on a one-off dyno, per gotcha #31 and the LAT-P058 precedent, with a
   spec addressed to the Integrator.
3. **The sentinel in scope**, per D4.
4. **The 46 gold probes as an armed control**, per D2.
