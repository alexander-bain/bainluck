# CAL-P185 — the group-key hazard is a proven four-link chain with a *scheduled* trigger, and the trigger the directive feared is the one that cannot fire

**Session:** CAL-P185, 2026-09-01 ~09:56–10:10Z / ~02:56–03:10 am PT. Directive `951`.
**Shipped code:** none, correctly. **Pushed:** nothing; remote == local verified.

---

## 0. One paragraph

Directive `951` ITEM 6 carried a hazard — `category` is a calibration **group key** that **neither
fingerprint sees**, so a mid-rebuild category rewrite can assemble one published curve from two
cohort labelings — and told the next session *"do not build a fix, do watch for it."* This session
watched it, and the watching moved it in both directions at once. **The trigger the directive
feared is harmless:** lane1's Q495 repair merged to master this session, and it writes only
`status='open'` rows while calibration reads only `status='resolved'` — **disjoint, it cannot touch
the curve.** **The trigger nobody named is real and scheduled:** `backfill_winners`
Phase 0-fix-categories rewrites `llm_sport_category` on `source='datagolf'` **with no status
filter**, every 6 hours, and `datagolf` is a source in the published curve. All four links are
proven at source, and the rewrite is invisible to **every** guard the build has. It is also,
measured right now, **quiescent: 0 rows**. So this is a loaded, undetectable, correctly-aimed gun
with an empty chamber — and a free one-line discriminator that says when it loads.

---

## 1. State verified this session

| thing | directive `951` said | measured |
|---|---|---|
| `origin/master` | `3ab15b20` | 🔴 **`f75563f9`** — master moved (3 merges) |
| do those merges reset the clock? | — | ✅ **No calibration source touched** (`git diff --name-only`) |
| live fingerprint | `e2040f90154fae876f0fb65f5abf74c3` | ✅ unchanged, and ✅ **reproduced locally** — no reset baked in |
| branch | `2f28aa30`, remote == local | ✅ confirmed via `git ls-remote` |
| ETA | `09-02T08:30–09:30Z` | ✅ **stands** |
| newest beat | `09:34:34Z`, bank 10 | ✅ same beat; next ~`10:34Z`, sampled ~`10:45Z` — outside this session |

The ⚡ local-fingerprint prediction from ITEM 3 step 1 works and costs one command. Use it:

```
cd backend && python3 -c "from app.tasks import precompute_calibration as pc; print(pc._main_input_fingerprint())"
```

It matched the live beat exactly, which is what licenses "the ETA stands" **without** waiting a beat.

---

## 2. The chain, link by link — all four proven at source

**Link 1 — `category` is a group key.** `calibration_staged_futures.py:208-214`,
`GROUP_KEY_COLUMNS = (bucket_idx, source, category, price_moved, is_nonexclusive_bundle)`. Rows
sharing this key merge into one published row.

**Link 2 — it is sourced from mutable market data.** `precompute_calibration.py:2851`:
`COALESCE(fm.llm_sport_category, 'uncategorized') AS category`.

**Link 3 — the fingerprint cannot see it.** `_main_input_fingerprint()` hashes
`inspect.getsource()` of four functions plus five named constants. **It hashes SOURCE TEXT AND
CONSTANTS. It reads no data at all.** A data-only change to `llm_sport_category` therefore *cannot*
move it, by construction — no reset, no discarded artifact, no signal.

**Link 4 — the drift check cannot see it either, and this is the new part.**
`roster_drift()` (`calibration_staged_futures.py:2062`) compares each banked unit's stored
`member_digest` against the plan's current one. `member_digest` digests
`vm_ids + market_ids + members`, where a member is the roster tuple
**`(market_id, source, vm_id, is_grouped)`** (`:675`, `:621`, `:931`). **`category` is not in that
tuple at either scope** — not in the per-unit `member_digest`, not in the global
`generation_fingerprint`. So a category rewrite moves no digest, and `staged:units_drifted` reads
`0` while the group key underneath the bank has changed.

⇒ **A mid-rebuild `category` rewrite is undetectable by all three guards simultaneously.** Units
banked before it carry the old cohort label, units after carry the new one, and both fold into one
published curve.

### 2a. This tests one of the directive's "still untested and quotable" gauges

`staged:units_drifted` is now **tested**, and the answer belongs with the other five gauges that
failed P181's question. It is *honest about what it measures* — banked units whose **roster
membership** moved — but its name invites the reading "units whose inputs moved", and **it is blind
to an entire class of input movement: any change to a group-key VALUE.** Membership drift ≠ input
drift. Do not quote `units_drifted: 0` as evidence that the bank is coherent.

---

## 3. The trigger the directive feared — ✅ CLOSED, it cannot fire

ITEM 6 flagged lane1's tennis/`table_tennis` cohort churn as the hazard's likely trigger. Their
Q495 **write** half merged to master this session (`58aa4680`, in `f75563f9`) as
`app/tasks/repair_polymarket_sport_category.py`, wired as an admin route with an `apply` flag, doing
exactly the feared thing: `UPDATE futures_markets SET llm_sport_category = :llm, category = ...`.

**It is nonetheless harmless to the curve, and the reason is a one-line population disjunction:**

- the repair writes **only** `WHERE ... status = 'open'` (`:173`, `:208`, `:355`, `:448`, `:470`);
- calibration's population reads **only** `WHERE fm.status = 'resolved'`
  (`_calibration_population_ctes`, line 138 of the CTE).

**Disjoint. Lane1 may run their repair with `apply=true` at any time, including mid-rebuild, without
any risk to the published curve.** 🔴 **Do not send them a "please defer" note — I nearly did, and
it would have been wrong.** The rows they fix are open now; they enter the curve only when they
later resolve, carrying whatever label they hold *at that point* — which is a normal ingest, not a
mid-rebuild rewrite.

---

## 4. The trigger nobody named — 🔴 REAL, SCHEDULED, STATUS-BLIND

`backfill_winners.py:6851-6868`, **Phase 0-fix-categories**, in the task that runs **every 6 hours**:

```sql
UPDATE futures_markets
SET llm_sport_category = 'golf'
WHERE source = 'datagolf'
  AND llm_sport_category != 'golf'
```

**There is no `status` filter.** It rewrites resolved rows.

And `datagolf` is not a bystander — it is a **source in the published curve**. Measured directly off
`GET /api/calibration`:

```
SOURCES IN PUBLISHED CURVE: ['datagolf', 'kalshi', 'odds_api', 'odds_api_bookmaker',
                             'odds_api_spreads', 'odds_api_totals', 'polymarket']
```

(Note in passing: **seven sources, not the "3 sources" CLAUDE.md's Calibration Pipeline paragraph
says.** Not this lane's to fix; parked as `P185-3`.)

The population applies **no `fm.source` whitelist** — it takes all sources and filters on
`fm.status='resolved'` + `fo.resolution_source IN CALIBRATION_TRUTH_ELIGIBLE_SOURCES`. The latter is
a **`resolution_source`** allowlist (how the winner was established), *not* an `fm.source` one; do
not confuse the two, they are different columns and I nearly graded on the wrong one.

The code's own comment confirms these rows reach the curve and that the misclassification is real,
not hypothetical:

> *LLM enrichment sometimes reclassifies them (e.g. "Volvo China Open" ended up as hockey, adding
> 3K+ golf outcomes to hockey calibration).*

**So the arming writer is enrichment and the correcting writer is Phase 0 — and both are
status-blind.** `futures.py:580-598` selects markets to reclassify on
`llm_sport_category IN ('other', NULL)` (or `== from_category`) with **no `status` predicate**, so a
*resolved* datagolf row can be re-labelled to `other`/hockey at any time, then flipped back to
`golf` by the next 6-hourly Phase 0 — potentially on opposite sides of a banked unit.

**During a ~26-hour rebuild, Phase 0 fires ~4 times.**

---

## 5. …and it is currently EMPTY. Measured, with the discriminator.

The UPDATE is **convergent**: it only changes rows that enrichment has re-misclassified. Right now
there are none.

```sql
SELECT llm_sport_category, status, count(*)
FROM futures_markets
WHERE source = 'datagolf' AND llm_sport_category IS DISTINCT FROM 'golf'
GROUP BY 1,2 ORDER BY 3 DESC
```
→ **`row_count: 0`** (12.1 ms, `sql_fingerprint 6a9f4b654e2f984c`, 2026-09-01 ~10:05Z).

`IS DISTINCT FROM` rather than `!=` deliberately, so NULLs count. **Zero means zero, including
NULLs** — and note the shipped UPDATE uses `!=`, which would *miss* a NULL row; a datagolf row that
enrichment set to NULL would be invisible to its own repair. Parked as part of `P185-2`, not fixed
here.

**⇒ The correct status is: armed, undetectable, correctly aimed, chamber empty.** Not an incident.
Not a reason to escalate. A thing to watch with one query.

🟢 **THE FREE DISCRIMINATOR — run this before trusting any published curve:** the query above. `0`
⇒ Phase 0 was a no-op across the rebuild and the bank is cohort-coherent for datagolf. **Non-zero
⇒ the gun is loaded and the next 6-hourly `backfill_winners` will rewrite a group key underneath a
partially-banked cursor, with `units_drifted` still reading 0.**

---

## 6. What I did NOT do, deliberately

- **Did not build a fix.** ITEM 6 is explicit: design question, needs a fold, ruling 134. Adding
  `category` to the roster tuple or to the fingerprint is a real design decision with a real cost
  (it would invalidate carried reads on every enrichment tick), and it is not a build-lane call.
- **Did not warn lane1.** §3 — their repair is provably disjoint from the curve. A warning would
  have been confidently wrong and would have cost them a deferral for nothing.
- **Did not file a new issue.** ITEM 5.6 stands. The hazard is already recorded on #2052; this
  session adds a correction comment there, in the pattern P184 used.
- **Did not push.** No code was written. `git ls-remote` confirms remote == local at `2f28aa30`.
- **Did not wait for the `10:34Z` beat.** It samples ~`10:45Z` and the decisive post-repair read is
  the twelfth beat, ~`18:30Z`. Waiting would have burned the session for one gauge tick.

---

## 7. For the next session

The directive's question #1 — *"is this thing already diagnosed, or already fixed, somewhere in our
own source?"* — paid again, and this time the answer came from a **docstring on a field**
(`UnitChunk.members`, `:675`) rather than a constant. **The roster tuple is written out in prose in
three places** and none of the three sessions that worried about the group-key hazard read any of
them. Reading `member_digest`'s docstring answers in 30 seconds what "does drift catch this?" would
otherwise take a fold to decide.

Generalised, for `docs/doctrine.md` if it ever earns a clause: **a guard's blind spot is usually
documented in the guard's own docstring, stated as what it *does* cover.** `roster_drift` says it
answers "how much has the roster moved" — and *roster* is defined, precisely, four fields wide,
one screen up.
