# CAL-P090 (#2098) — the source-carrying join, BUILT on `program/calibration-88`

**Built 2026-08-24 by CAL-P090 (calibration lane, window `pid:66937-cal-p090`), on the
Fable directive of the same day (item 3), pasted and reviewed by Alex.**

**Status: BUILT, NOT MERGE-ELIGIBLE.** Three obligations named by the staged spec
(`cal-p088-2098-staged-fix-and-cert.md`) are OWED and unmet, and they are listed in §5
before anything else in this file can be read as a green light. Flagged for
**cert C-2098-SOURCE-1** against the branch head. **Not self-certified.**

Authority: **ruling 125** —
`docs/rulings/125-a-row-deleting-join-must-carry-every-dimension-that-identifies-the-row.md`.
The judgment that the behaviour is wrong was banked in CAL-P088, ahead of this fix, by
design. What follows is only the change and the evidence around it.

---

## 1. What shipped

`backend/app/tasks/precompute_calibration.py`, in `_calibration_population_ctes()`:

```sql
mode_prices AS (
    SELECT vm_id, source, adj_opening_probability AS mode_price   -- + source
    ...
    GROUP BY vm_id, source, adj_opening_probability, eligible     -- + source
    HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
),
deduped AS (
    SELECT ro.* FROM normalized ro
    LEFT JOIN mode_prices mp
      ON mp.vm_id = ro.vm_id
      AND mp.source = ro.source                                   -- + this line
      AND mp.mode_price = ro.adj_opening_probability
```

**Correction to the staged spec: this is THREE lines, not two.** §1 of
`cal-p088-2098-staged-fix-and-cert.md` names the `GROUP BY` and the join conjunct and
omits the projection. `mode_prices` must also SELECT `source`, or the new conjunct
cannot be written at all. Recorded here rather than left as a discrepancy between the
spec and the diff — the spec's "two lines. The size of the diff is not the size of the
obligation" survives intact; the count was simply off by one.

### Why the defect existed

`vm_id` is source-blind on its `e:` arm: `virtual_market` builds it as
`'e:' || event_id`, while `event_sizes` counts per `(event_id, source)`. So two sources
each carrying ≥3 resolved markets on one event are assigned the SAME `vm_id`. Every
neighbouring aggregate is source-scoped deliberately — `vm_stats` GROUPs BY
`(vm_id, source)`, `clean_vms` JOINs on both — and `mode_prices` was the one that was
not.

Verified live today (2026-08-24, `db-query`, `sql_fingerprint 048521d2738c1403`):

| event_id | source | resolved markets |
|---|---|---|
| 14887630 | kalshi | 26 |
| 14887630 | polymarket | 171 |

Both clear `event_size >= 3`, so both are assigned `e:14887630`. The specimen's premise
holds today, not merely on 2026-08-22.

---

## 2. The regression guard (cert §3d)

`backend/tests/integration/test_calibration_mode_price_source_scope_pg.py`, wired into
CI's `search-recall` job (the one job with a real `postgres:15` service), with the same
skip-detection every other gate in that job carries — a silently-skipped gate reads
exactly like a passing one.

§3d requires a fixture, explicitly **not** a string assertion on the SQL, because
"string assertions on frozen SQL have already produced one false sense of coverage in
this module's history." The fixture seeds one `event_id` reachable from two sources:

* **kalshi**, 5 legs at `0.5, 0.5, 0.25, 0.125, 0.625`. At `eligible = 5` its own mode
  needs `count > GREATEST(2.5, 2) = 2.5`, and 2 is not — so Kalshi forms **no** mode of
  its own and every leg is publishable on its own merits. Anything that deletes one came
  from the other source.
* **polymarket**, 4 legs all at `0.5`. At `eligible = 4` its mode needs `count > 2`, and
  4 is — so these four **should** be deleted, by their own mode, among themselves.

Four arms:

1. **The premise, asserted rather than assumed.** Both sources really do share one
   `vm_id` and really do carry their own source-scoped `eligible`. If `vm_id` ever
   becomes source-carrying, the gate says so by name instead of passing vacuously.
2. **The fix.** All 5 Kalshi legs publish, including the two at Polymarket's modal price.
3. **The falsifier.** Polymarket's own 4 legs are STILL deleted. The fix must SCOPE the
   mechanism, not disable it — a fix that restores rows by breaking dedup is worse than
   the defect.
4. **The control** (a second test): a single-source event is unaffected. Kalshi alone,
   3 of 4 legs at `0.5`, still deleted. This is cert §3a's 0.000-pp control-cell
   prediction expressed as a unit fact.

### RED-FIRST, proved in the same run

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`; measured
again this window), so this file could not be run red on the lane's machine before the
fix landed. Rather than assert red-first on my word, the file is **two-armed**, the
pattern `tests/integration/test_create_wave_insert_bind_contract.py` already establishes
in this same CI job: `test_red_first_the_reverted_join_still_reproduces_the_suppression`
reconstructs the PRE-fix statement by reverting the three substitutions and **executes
it**, asserting that Polymarket's mode deletes the two Kalshi legs at `0.5`.

`_revert_the_fix()` asserts each substitution matches **exactly once**. A revert arm
that silently failed to revert would run the FIXED sql, observe no suppression, and
report that red-first was proved — gotcha #53's failure shape wearing a test's clothes.

**Still owed to the cert:** a green CI run of that job. The lane does not push, so no run
exists yet. The certifier should treat "the guard is written and wired" and "the guard
has run" as two different claims, and this file only makes the first.

---

## 3. Re-baseline declaration — MEASURED, not estimated (cert §2, second box)

`_main_input_fingerprint()` hashes `inspect.getsource(_calibration_population_ctes)`, so
this edit moves it. Every banked unit is invalidated and the convergence count restarts
from zero. The spec requires the discarded unit count be **measured**. Read from
production `GET /api/calibration` → `staged`, **2026-08-24 16:57 UTC (09:57 PDT)**:

```
staged_at                 2026-08-24T11:38:20+00:00
units_banked              128
units_this_beat             8
units_drifted             128
units_drift_checkable     128
units_drift_unknown         0
frozen_over_drift          true
rebuild_units_banked       44
rebuild_units_this_beat     8
rolling_restage            true
```

**The 128-unit bank is already worthless and the fix is not what costs it.** All 128 are
drifted, 0 are drift-unknown, and `frozen_over_drift` is true — the bank is already held
back from publishing. The real discard is the **44-unit rebuild bank** plus the 8 units
of the beat in flight. That is the measured price of this deploy, and it is smaller than
the spec's framing anticipated. It is stated here as a number so the certifier can check
it rather than accept it.

**`CALIBRATION_POPULATION_VERSION` is deliberately NOT bumped, and that is a decision,
not an omission.** A bump additionally invalidates the 7-day last-good artifact, and the
module's own comment block records that the 2026-08-02 attempt "was reverted within the
hour" because `snapshot_verdict` refused the artifact and `/calibration` went dark until
the next successful build — unbounded, on a task known to overrun its window. Source
hashing already delivers the correct invalidation. A version bump is a Fable/Alex call
with a page-darkening cost attached; this lane does not make it. If the certifier
believes the population change warrants one, that is an escalation, not a lane fix.

---

## 4. Two more sites with the identical defect — REPORTED, NOT FIXED

Ruling 125's clause is general, and `mode_prices` is copied twice more in the tree. Both
are **outside this cert's scope** and both are left alone deliberately: widening a cert
scoped to one frozen producer into a route file and an ad-hoc script is exactly the
blast-radius growth the queue discipline exists to prevent. Staged, not silent:

| File | Lines | Note |
|---|---|---|
| `backend/app/routes/admin_data_quality.py` | 1693–1703 | **Not frozen.** Same `GROUP BY vm_id, …` and same bare-`vm_id` join. Its own neighbour `clean_vms` at :1684 correctly joins `cv.vm_id = vm.vm_id AND cv.source = vm.source` — corroborating that every surrounding aggregate is source-scoped on purpose and this one is the outlier. Consequence: this admin audit endpoint will now DISAGREE with the producer about the published population by ~35 rows, and will keep reporting the defect as live. |
| `backend/scripts/audit_golf_hockey_calibration.py` | 167–178 | Ad-hoc audit script, same shape, same consequence at much smaller stakes. |

Recommend a follow-on queue item covering both, carrying ruling 125 as its authority and
needing no new judgment.

---

## 5. WHAT IS OWED — read this before scheduling a merge

`cal-p088-2098-staged-fix-and-cert.md` §0 states this item is "**blocked behind** the
apply, not merely ordered after it". None of that changed. What this window produced is
the CODE, on a branch, so it is ready when the gates open — not permission to open them.

1. **Ruling 009's named freeze exception DOES NOT EXIST.** `precompute_calibration.py`
   is frozen until `calibration:main` publishes fresh post-CAL-P024 and converges. Spec
   §2 requires "a named exception granted by the freeze's owner, recorded the way
   `GO-CAL-P078-HINDSIGHT-EXCLUSION-EXCEPTION.md` was." No `GO-CAL-P090-*` file exists
   on disk; I checked. **Ruling 009 says a change that genuinely cannot wait is an Alex
   escalation, not a lane call** — so this branch is the escalation's artifact, not its
   resolution. The freeze's harm is a function of DEPLOYS to the producer, not of commits
   on an unmerged branch, and merge order is the Integrator's; that is the whole reason
   building was judged safe while merging is not.
2. **The sequencing gate is CLOSED.** Spec §0 requires the `-86` deploy, then the
   attended `--bank` fold, then Gate 5's first real verdict, then the hindsight-exclusion
   apply — and only then this item. Measured earlier this same window: the §5c pre-flight
   returned **GATE CLOSED** (all three `payload_*_status` fields ABSENT; artifact dated
   `2026-08-21T19:24:23Z`), `origin/master` is still `81380151`, the deployed slug v3885
   equals it, and `-85`/`-86`/`-87` are not ancestors of it. Merging `-88` ahead of that
   chain would move `_main_input_fingerprint()` while Gate 5 is still waiting on its
   first successful fold — destroying the population the fold exists to measure, exactly
   as §0 predicts.
3. **The cert has not been run, and must not be run by me.** C-2098-SOURCE-1 owns §3a's
   control cells, §3b's restored-row correctness on the real `e:14887630`, §3c's
   before/after ECE-MCE pair from one fold, and the `deduped` +35 row-count proof.
   Instrument B of `backend/scripts/measure_2098_mode_price_collision.py` is unchanged
   and still produces the before; Instrument A is now direction-aware (see §6) so the
   pre-fix chain is still reconstructable from post-fix source.

---

## 6. `measure_2098_mode_price_collision.py` survives its own subject being fixed

The script's `build_chains()` used to synthesise the source-SCOPED chain from
production's source-BLIND one. Production is now the scoped one, so the anchors would
have found nothing. Left alone it would have aborted; patched carelessly it would have
substituted nothing and compared a fold against itself — planning two identical costs and
reading as "the source-blindness costs nothing", the flattering direction arrived at by
measuring nothing.

It is now **direction-aware**: it detects which side of the fix the checked-out source is
on, reconstructs the other, and **refuses loudly** if it matches neither. `JOIN_TO` is
pinned to the three-line form CAL-P090 actually shipped, verbatim, because the anchors
are also read in reverse and an anchor that is merely equivalent finds nothing.

Instrument B (`--out`, the chunked upper bound that produced the 35-row measurement) is
untouched and unaffected — its SQL is a hand-written literal that builds both mode groups
itself.

---

## 7. What this change does NOT do

* **It does not reopen source-chunking (#2076).** Spec §5. Chunking was closed on cost
  and on the measured pushdown, independently of this defect; removing one objection is
  not an argument. And the chunking invariant it fed does **not** rest on `mode_prices`
  alone: the representative window is still `ROW_NUMBER() OVER (PARTITION BY cv.vm_id …)`
  — source-blind — so "a `vm_id` is never split" survives this fix on its second leg.
  (That window is not a live cross-source defect: sharing an `e:` `vm_id` requires
  `event_size >= 3` on BOTH sources, which makes both `is_grouped`, hence `is_multi`,
  hence the `ELSE ro.rn = 1` branch is never the one that decides them. It is computed
  cross-source and not consulted.) The prose in
  `app/utils/calibration_staged_futures.py` and
  `app/tasks/calibration_published_twin_worker.py` that cites `mode_prices` as a live
  source-blind peer mechanism is now stale on that one leg; correcting it is comment-only
  and is left to the follow-on in §4 rather than mixed into a frozen-file cert.
* **It does not change `vm_id`.** Making the id source-carrying is a much larger
  re-baseline across the `g:`, `e:` and `m:` arms and every downstream key. The join is
  where the defect acts; the join is where it is fixed.
* **It does not re-grade or mutate anything.** Read-side only, gotcha #21.

---

## 8. Files changed

| File | Change |
|---|---|
| `backend/app/tasks/precompute_calibration.py` | the three lines + the ruling-125 comment block |
| `backend/tests/integration/test_calibration_mode_price_source_scope_pg.py` | NEW — the two-armed real-Postgres guard |
| `.github/workflows/ci.yml` | NEW step in `search-recall`, with skip-detection |
| `backend/tests/evals/fixtures/calibration_fingerprint_derived_map.json` | `source_sha256` only — the fingerprint moved, which is the point |
| `backend/scripts/measure_2098_mode_price_collision.py` | direction-aware `build_chains()`; `JOIN_TO` pinned to the shipped form |
| `docs/audits/calibration/cal-p090-2098-source-scope-fix.md` | this file |

No migration. No beat-schedule edit. No new ruling banked (125 already covers it).
