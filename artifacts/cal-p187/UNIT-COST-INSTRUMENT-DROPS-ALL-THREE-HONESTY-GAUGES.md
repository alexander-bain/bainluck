# CAL-P187 — the beat-gauge instrument publishes the unit cost its own author labelled wrong, and drops all three gauges built to qualify it

**Session:** CAL-P187, 2026-09-01 ~11:00Z / ~04:00 am PT
**Question applied:** P185/P186's, now three for three —
***"what, exactly, does this instrument capture, and what is therefore NOT in it?"***
**Target:** `staged:unit_ms_mean` — named "untested and quotable" by directives 952 and 953
(*"`unit_ms_mean`'s denominator on a cancelled beat"*).
**Artifact read:** `GET /api/admin/calibration-beat-gauges?full=true`, 168 observations,
`artifact_generated_at 2026-09-01T10:45:00.331278Z`, newest beat `10:32:30.538856Z`.

---

## 1. THE NARROW ANSWER TO THE QUESTION AS ASKED

**`unit_ms_mean`'s denominator on a cancelled beat is `units_this_beat`, not
`units_completed_this_beat`** — every unit the beat *timed*, including the ones killed at their
own bound.

Traced, not guessed. Two functions write the key `staged:unit_ms_mean`:

| writer | file:line | call | denominator | when it runs |
|---|---|---|---|---|
| `_record_convergence_projection` | `precompute_calibration.py:4449-4450` | `record_stage` (**accumulates**) | `ran_this_beat` | mid-beat, after the unit loop — **skipped by a throw** |
| `_record_staged_rate` | `calibration_main_build.py:1584` | `record_gauge` (**overwrites**) | `ledger.stage_counts["read:futures_unit"]` | inside `save_phase_ledger`, on **every** terminal |

Both write **the same dict** — `record_gauge` is `self.stages[name] = int(value)`
(`calibration_phase_ledger.py:1315`), `record_stage` is `self.stages[name] = get(name,0) + ms`
(`:1248`). 🟢 **They do not corrupt each other, and the order is the safe one:**
`save_phase_ledger` runs last, so the overwriting gauge always wins over the accumulating stage.
**There is no double-count. Do not go looking for one.**

So the value on the wire is `stage_mean_ms()`, whose own docstring
(`calibration_phase_ledger.py:1263-1265`) says it plainly:

> *"Note this is the MIXED mean … It is the right number for attributing elapsed time and **the
> wrong one for costing a unit**; use `stage_completed_mean_ms` for the latter."*

**This confirms P182 and adds the mechanism. It is not a re-litigation — P182 was right.**

---

## 2. 🔴 THE ACTUAL FINDING — THE CORRECT NUMBER EXISTS, IS WRITTEN EVERY BEAT, AND THE SAMPLER THROWS IT AWAY

CAL-P067 and CAL-P068 already found what §1 says, and built a **three-part apparatus** so no reader
could ever mistake a truncated observation for a cost. All three parts are written into the ledger
on every beat. **The beat-gauge sampler captures none of them.**

| gauge | written at | what it is for | captured |
|---|---|---|---|
| `staged:unit_ms_mean_completed` | `calibration_main_build.py:1577` | the **cost-correct** mean — CAL-P067's whole point, "recorded beside the mixed one rather than replacing it" | 🔴 **0 / 168** |
| `staged:unit_cost_reason:no_unit_completed` | `:1574-1576` | the marker for *"every unit this beat was cancelled … the state in which **no unit cost may be quoted at all**"* | 🔴 **0 / 168** |
| `staged:beats_basis:completed` / `:mixed` | `:1613-1615` | which mean the projection used, written expressly so *"a number derived from a lower bound and a number derived from a duration **must not render identically** (ruling 075, second clause)"* | 🔴 **0 / 168** |

Cause, and it is one line: `calibration_beat_gauge_sampler.py:167-177`. `select_gauges` captures
exactly `REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES`, plus a prefix sweep for
`CONVERGENCE_REASON_PREFIX = "staged:convergence_reason:"` (`:135`). `OPERATIONAL_GAUGES` lists
`staged:unit_ms_mean` and **not** its completed twin; `unit_cost_reason:` and `beats_basis:` are
different prefixes, so the one prefix sweep does not reach them. Verified empirically — the 168
observations carry **18 distinct gauge keys** and none of the three is among them.

**So the instrument keeps the number labelled wrong-for-costing, and drops the replacement, the
"do not quote a cost at all" flag, and the provenance flag — all three.**

### The loss is IRREVERSIBLE from the captured set

Given `units_this_beat`, `units_completed_this_beat` and the mixed `unit_ms_mean`, the completed-only
mean **cannot be backed out**: the cancelled units' elapsed times are not captured, and
`mixed_total − completed_total` has two unknowns. **No amount of re-reading the existing artifact
recovers it. It has to be captured going forward or not at all.**

---

## 3. WHAT IT COSTS, MEASURED ON THE 168-BEAT WINDOW

**34% of every unit cost this instrument has ever published is not a unit cost.**

| | beats |
|---|--:|
| beats publishing a `unit_ms_mean` | **164** |
| …contaminated — some units cancelled, mixed ≠ completed | **53** (32%) |
| …🔴 **UNQUOTABLE — `units_completed_this_beat: 0`, every unit cancelled** | **2** |
| **total that are not a valid unit cost** | **55 = 34%** |

The two unquotable beats are the sharp ones. Both ran a unit, completed none, and **still published
a plausible-looking cost** while the flag that says *"no unit cost may be quoted at all"* was
written into the ledger and dropped on the floor:

| beat | `unit_ms_mean` | this_beat / completed | where it ranks among all 164 published costs |
|---|--:|:--:|---|
| `2026-08-28T01:21:20Z` | **180,858 ms** | 1 / 0 | **29th — 82nd percentile** |
| `2026-08-28T22:20:23Z` | **77,156 ms** | 1 / 0 | **161st — 2nd percentile** |

🔴 **Neither is an outlier.** One reads high-normal, one reads low-normal. A reader scanning the
column has nothing — no flag, no gap, no anomaly — to tell them these two rows are lower bounds on
units that never finished. **That is precisely the failure ruling 075's second clause names**, and
CAL-P067 built the gauge that prevents it. It just never reaches the instrument.

⚠️ **What this artifact does NOT measure: the magnitude of the bias.** The mixed-beat median
(144,680 ms) is *higher* than the clean-beat median (137,853 ms), but that is a **cross-beat**
comparison between two different populations — beats cancel *because* they are slow — and it is
confounded. It is **not** a bias measurement and must not be quoted as one. CAL-P068 documents the
within-beat direction (`calibration_main_build.py:1601-1606`): a truncated observation drags the
mean **DOWN** → more units appear to fit → **fewer** beats appear to remain → the projection is
**optimistic by construction**. 🔴 **The within-beat magnitude cannot be measured from this
artifact at all, because measuring it requires the completed-only mean the sampler drops. The
instrument cannot measure its own known bias.** This is the second-order cost of the omission and
the reason it is worth more than "a column in a report".

### It also explains a standing mystery, partly

P181 found `beats_to_publish` *"floors at 1; 13% accurate"*. CAL-P068 made that projection use the
completed-only mean **when one exists**, falling back to the mixed mean when it does not, and
recorded `beats_basis:*` to say which. Since that flag is uncaptured, **you cannot tell which of the
164 projections were computed on a duration and which on a lower bound.** Any attempt to model
`beats_to_publish`'s accuracy across this window is mixing two different estimators with no way to
separate them. *(Not a new finding about `beats_to_publish` — a named obstacle to ever making one.)*

---

## 4. 🟢 THE FIX IS THREE STRINGS AND IS PROVABLY WIPE-SAFE — AND IS STILL NOT THIS LANE'S TO BUILD

The repair is appending three names to `OPERATIONAL_GAUGES` (plus one prefix sweep, or listing
`beats_basis:` both ways) in `calibration_beat_gauge_sampler.py`.

🟢 **It cannot wipe the rebuild, and that is proven, not assumed.** `_main_input_fingerprint()`
(`precompute_calibration.py`) hashes `inspect.getsource()` of exactly four functions —
`compute_calibration_payload`, `_calibration_population_ctes`, `_virtual_market_ctes`,
`_main_futures_sql` — plus five named constants. **`calibration_beat_gauge_sampler.py` is not among
them and is not called by any of them.** A sampler-only edit cannot move the digest by construction.
So this is **not** what D-G's freeze is about; D-G names `precompute_calibration.py`.

🔴 **And it still does not get built here.** Under CLAUDE.md's PROGRESS-NOT-MEASUREMENT and ruling
134, a change that improves an instrument and nothing a user sees **has no ship**, and a queue that
cannot name one does not get run. Wipe-safety removes the *risk*; it does not supply the *ship*.
**Parked as `P187-1`, for the measurement lane, to be spent when a named ship needs the unit cost to
be trustworthy** — the obvious candidate being any future attempt to make `beats_to_publish` a real
ETA, which per §3 is blocked on exactly these three gauges.

⚠️ **Honest note on the author's intent, recorded so this is not read as an accusation.** The
sampler's own docstring (`:161-166`) says `OPERATIONAL_GAUGES` *"is the sampler's own editorial
choice and is allowed to be hand-maintained — forgetting one costs a column in a report, not the
replayability of the row."* That is true of the *row's replayability* and this finding does not
dispute it. The narrow correction is that for **these particular three** the cost is higher than the
docstring's estimate, because they are not decoration — they are the qualifiers that stop a lower
bound from rendering as a duration. **The row is still replayable. The unit cost on it is still not
always a unit cost.**

---

## 5. FOR THE NEXT SESSION

🆕 **Trap 22 — `staged:unit_ms_mean` on the beat-gauge artifact is a MIXED mean over every unit the
beat TIMED, and 34% of its readings are not a unit cost — 2 of them from beats where nothing
completed at all, both rendering as perfectly ordinary values.** The three gauges that would tell
you which (`unit_ms_mean_completed`, `unit_cost_reason:no_unit_completed`, `beats_basis:*`) are
written every beat and captured on none. **Never quote `unit_ms_mean` as the cost of a unit without
checking `units_completed_this_beat == units_this_beat` on the same row.** When they differ, the
number is contaminated; when `units_completed_this_beat` is 0, there is no cost on that row at all.

**Moves off the untested list:** `staged:unit_ms_mean`'s denominator — **answered** (§1), and the
answer opened §2. **Still untested and quotable:** `staged:generation`.

**Scoreboard for the question that keeps paying** — *"what does this thing compare/capture, and what
is therefore NOT in it?"* — now **three for three**: P185 (`units_drifted` omits `category`),
P186 (`served_drifted` is a saturating slot count with no magnitude), P187 (the unit-cost
instrument drops all three of its own honesty gauges). 🔴 **All three answers were written out, in
plain English, in the docstring of the thing being read. Read the docstring of the constant before
theorising about the number.**

---

## 6. LIVE STATE AT CLOSE — and the finding caught in the act

**Beat `2026-09-01T11:32:41.898424Z`** (sampled `11:48:16.463404Z`), fingerprint **`e2040f90`
unchanged — no fifth reset**: `units_banked` **20** (15 → 20, **+5**), `units_this_beat` 7,
`units_completed_this_beat` **5**, `units_cancelled` 2, `served_units` 0, `terminal: cancelled`,
`gate: not_evaluated`, `disclosure.reason: served_at_absent`, `units_drifted` **0** (back from 5;
membership-only, P185 — not a signal), `beats_to_publish` 6 (**not an ETA**, P181).

🆕 **This beat is itself a Trap 22 instance, live.** It publishes `unit_ms_mean = 146,396 ms` over
`units_this_beat 7` / `units_completed_this_beat 5` — **a contaminated reading**, and the
`unit_ms_mean_completed` that would correct it was written into the ledger this beat and dropped by
the sampler. The previous beat's 144,680 ms is likewise contaminated, and is *exactly* the
mixed-beat median quoted in §3. **The reader has no way to tell from the artifact.**

**⏱ ETA — `09-02T08:30–09:30Z`, a FOURTH confirmation**, and the first derived twice within one
session from two consecutive live beats that agree:

| from | bank | to band 122–127 | to full 128 |
|---|--:|---|---|
| `10:32Z` | 15/128 | 22 beats → `09-02T08:32Z` | 23 beats → `09-02T09:32Z` |
| `11:32Z` | 20/128 | 21 beats → `09-02T08:32Z` | 22 beats → `09-02T09:32Z` |

🟡 **The fence repair (v3970, live `06:54:25Z`) has still moved nothing — FIVE post-repair beats
(`07:31`, `08:31`, `09:34`, `10:32`, `11:32`), all `units_completed_this_beat: 5`, all cancelling at
2.** **Still not the verdict** — the directive sets that at the twelfth beat (~`09-01T18:30Z`).

🟢 **`origin/master` MOVED this session, `f75563f9` → `7d066c50`, and the clock survived it.** Three
lane1 commits (q496 table-tennis drain / CERT-667, q067 game-completion / CERT-668) touching
`admin_repairs.py`, `odds_polling.py`, `repair_polymarket_sport_category.py` and two test files.
**No calibration source in the diff**; `precompute_calibration.py`, `calibration_main_build.py`,
`calibration_staged_futures.py` and `calibration_phase_ledger.py` are all byte-identical between
HEAD and `origin/master`, and the predictor at HEAD still reproduces the live `e2040f90`.
**The ETA stands. This is the check paying for itself — master moved, and the answer is "harmless",
which is only sayable because it was run.**

🟢 **P185's datagolf group-key discriminator re-run `10:52Z`: 0 rows.** Still quiescent — three
sessions running (P185 `10:05Z`, P186 `10:07Z`, P187 `10:52Z`).
