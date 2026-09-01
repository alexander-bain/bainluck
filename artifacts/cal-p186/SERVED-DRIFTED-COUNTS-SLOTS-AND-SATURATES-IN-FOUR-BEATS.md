# CAL-P186 — `staged:served_drifted` is a SLOT counter that saturates in ~4 beats

**Session:** CAL-P186, 2026-09-01 ~10:10Z / ~03:10 am PT
**Instrument:** `GET /api/admin/calibration-beat-gauges?full=true`, 168 observations, sampled
`2026-09-01T09:45:07Z` (P185's artifact — no new beat had landed when the analysis was run).
**Source read:** `calibration_staged_futures.py:1919-1943` (`served_drift`), `:1854-1864`
(`promote_if_complete`), `:1867-1899` (`top_up_served_digests`), `:1976-2059`
(`retain_planned_units`); `calibration_main_build.py:1471-1523` (`_record_served_bank`).

The directive (`952`, ITEM 3 step 6) listed `staged:served_drifted` as **untested and quotable** —
*"reads 128 on many beats — of what?"*. This answers it. Applying P185's question: **what does this
guard compare, and what is therefore NOT in it?**

---

## 1. WHAT IT COMPARES

`served_drift(cursor, chunks)` is one expression:

```python
sum(1 for name in cursor.served_units
    if name in cursor.served_digests
    and name in current
    and current[name] != cursor.served_digests[name])
```

- `name` iterates **`served_units`** — the 128 unit keys. Since CAL-P028 a unit key is the
  **SLOT** `(buckets, index)` of the partition, not a market.
- `current[name]` is the plan's **`member_digest`** for that slot, whose roster tuple is
  `(market_id, source, vm_id, is_grouped)` — P185's finding, unchanged here.
- The baseline `cursor.served_digests` is **frozen at promotion** and never re-stamped.
  `top_up_served_digests` *"only ever ADDS"* (`:1885`) — deliberately, and the docstring gives
  CAL-P016's reason: re-stamping before measuring makes drift read zero forever.

So the gauge is a **cumulative-since-promotion count of SLOTS whose membership tuple has changed
at least once**, with a hard ceiling of 128.

### What is therefore NOT in it

1. 🔴 **MAGNITUDE.** It is `sum(1 ...)` per slot. `served_drifted: 128` is satisfied by one new
   market per slot *or* by a thousand. There is no gauge anywhere that says how much the served
   roster moved — only how many of the 128 slots moved at all.
2. 🔴 **`category`.** Same blind spot P185 found in `roster_drift`: `category` is a
   `GROUP_KEY_COLUMNS` member but is absent from the roster tuple the digest hashes. Both twins
   inherit it.
3. **DIRECTION.** Arrival, departure and re-labelling are indistinguishable.

## 2. IT SATURATES — MEASURED, 7 PROMOTIONS

Its baseline never re-stamps, so it can only ratchet up until the next promotion resets it.
Measured over the 126 observations that had a served census:

| promotion | reached 128 after | path (`served_drifted` per beat) |
|---|---|---|
| 2026-08-26T09:27:40 | 5 beats / 5.2 h | `0, 71, 78, 115, 115, 128` |
| 2026-08-27T02:33:48 | 4 beats / 4.1 h | `0, 28, 118, 127, 128` |
| 2026-08-27T23:16:32 | 6 beats / 6.1 h | `0, 117, 117, 121, 125, 125, 128` |
| 2026-08-28T20:37:42 | 4 beats / 4.0 h | `0, 94, 94, 109, 128` |
| 2026-08-29T20:21:15 | 2 beats / 2.2 h | `0, 127, 128` |
| 2026-08-30T12:25:53 | 3 beats / 3.2 h | `0, 115, 126, 128` |
| 2026-08-31T02:19:05 | 2 beats / 2.3 h | `0, 126, 128` |

**Median 4 beats / 4.0 h. Range 2–6.** 7 of 7 promotions saturated; none failed to.

**The first beat carries almost all of it.** One beat after promotion the reading is already
`71, 28, 118, 94, 127, 115, 126` — **median 115/128, i.e. 90% of ceiling within a single hour.**

**84 of the 126 served beats (67%) read exactly 128** — pinned, unable to move in either direction.

The serving bank is meant to live for a whole rebuild cycle (~26 h at the current rate). The gauge
spends its first hour going to 90%, saturates by hour four, and is **information-free for roughly
the last 85% of the census's serving life.**

## 3. WHAT IS *NOT* WRONG — TWO NON-FINDINGS, RECORDED SO NOBODY RE-CHASES THEM

- 🟢 **The promotion-beat reading is not a crossed gauge.** On promotion beats the artifact shows
  `(units_drifted=114, served_drifted=0, units_banked=0)`. Read naively against
  `retain_planned_units:2009` (`cursor, served_moved, drift = promoted, drift, 0`) that looks
  exactly inverted, and it is tempting to file it. It is correct: on those beats promotion happened
  inside `advance()` mid-beat, and `promote_if_complete` hard-sets `served_drift_units=0`
  (`:1860`) while `roster_drift_units` keeps what retention measured at the top of the beat.
  **Do not file a crossed-gauge bug.**
- 🟢 **The frozen baseline is not a defect.** It is CAL-P016's ordering rule, stated in the
  docstring at `:1885-1888`. Re-stamping would be the actual bug. Saturation is the *price* of
  correctness here, not a symptom of anything broken.

The gauge is honest. It is simply **spent**, almost immediately, and its name does not say so.

## 4. 🔴 THE TRAP THIS SETS FOR THE NEXT SESSION — THE ONE THAT GRADES THE SHIP

The current rebuild's ETA is `09-02T08:30–09:30Z`. When it promotes:

- the promotion beat will read **`served_drifted: 0`**,
- ~1 h later it will read **~115**,
- within ~4 h it will read **128** and stay there.

**None of that is a failure of the new curve.** It is what every one of the last seven healthy
promotions did. A grader who sees `served_drifted: 128` beside a freshly published curve and reads
it as staleness or breakage will be repeating a misread this lane has already killed once — the
directive's dead-hypothesis list contains *"100% drift causes the refusal"* for exactly this reason.

**Grade the ship on `served_at` / `served_units` / `terminal` (CAL-P169(a)), never on
`served_drifted`.** It saturates on a healthy curve by construction.

## 5. SIDE OBSERVATION — SATURATION IS GETTING FASTER (not actioned)

Beats-to-saturate across the seven promotions, in time order: **5, 4, 6, 4, 2, 3, 2**. The last
three are the fastest three. On a 7-point series that is suggestive, not established — it is exactly
the shape P183's question warns about (*"has this rate CHANGED, or am I quoting a median across two
regimes?"*), and it would need a longer window and a magnitude gauge (which does not exist, §1.1) to
say anything real. **Parked, not claimed.**

## 6. THREE MORE GAUGES OFF THE DIRECTIVE'S UNTESTED LIST — cheap, weak results, recorded anyway

- **`summary` vs `summary_as_banked`: IDENTICAL on all 11 fields** at this beat. But
  `served_units` is currently 0, which is the condition under which they would be expected to
  coincide, so this is **not** a test that they can never differ. **Re-run it after publication** —
  that is the only state that can discriminate them. Recorded so the next session knows the cheap
  check has been done and what it did *not* settle.
- **`envelope_complete`: `True` on all 168 beats. Zero observed variance.** A flag that has never
  once been false in the entire retained window carries no information about any beat in it. Not
  a defect — possibly it only trips on a shape this window never saw — but it is not evidence of
  health either, and it should not be quoted as if it were.
- **`measured`** is exactly the complement of the `served_at` gap: `True` on 126, `False` on the
  same 42 beats whose `gauges_missing_required == ('staged:served_at',)`. **Honest, consistent with
  the disclosure logic, no surprise. Do not re-check.**

### 6a. 🟢 A BONUS RESULT — and it started as a WRONG GUESS of mine

I first wrote into the successor directive that `staged:units_done` and `staged:units_banked`
*"read equal on every beat — is one redundant?"*. **Checking it before shipping the claim killed
it: they differ on 27 of 168 beats**, and the difference is the useful part.

Measured signatures, no exceptions in the window:

| event | `units_done` | `units_banked` | `served_units` | n |
|---|--:|--:|--:|--:|
| **PROMOTION** | **128** | **0** | **128** | 7 |
| **WIPE** (fingerprint change) | **5** | **5** | **0** | 3 (all 3 fp changes) |

So `units_done` is **not** redundant — it is a second, independent confirmation of CAL-P169(a)'s
rule that *a bank of 0 is a win, not a reset*. A promoted bank reads `(128, 0)`; **a wipe never
looks like that at all.** The two gauges are evidently sampled on opposite sides of promotion within
the beat, which is why the promotion beat maximises their gap.

⚠️ **`units_done` is ABSENT — not `0` — on 3 beats.** The writer records it deliberately even when
`ran_this_beat` is 0 (`precompute_calibration.py:4438-4441`, citing gotcha #53: *"an absent stage
reads as fine"*). So absent means **the beat died before that stage ran**, not that nothing
completed. Two different facts; do not collapse them.

**Method note, and the point of writing this section down:** the claim was cheap to check and
cheap to have been wrong about — but it was already typed into a handoff that the next session
would have inherited as fact. The directive's own rule (*"is this gauge actually measuring what its
name says?"*) applies to the sentences a session writes, not only to the ones it reads.

## 7. STATE VERIFIED THIS SESSION (all measured, none inherited)

- Local fingerprint at HEAD `e2040f90154fae876f0fb65f5abf74c3` — **reproduces the live beat. Clock
  clean, no reset baked in, ETA `09-02T08:30–09:30Z` stands.**
- `origin/master` = `f75563f9` — **unmoved** since P185.
- Branch `program/calibration-168-rank1-baseball` @ `2f28aa30`; `git ls-remote` confirms
  **remote == local**. Only the two auto-generated heartbeat JSONs dirty, correctly uncommitted.
- P185's datagolf discriminator re-run at `10:07Z`: **0 rows. Still quiescent.**
- 🆕 **A NEW BEAT LANDED AND WAS READ — `2026-09-01T10:32:30.538856Z`, artifact `10:45:00.331278Z`.**
  `input_fingerprint` **still `e2040f90`** ⇒ **no fifth reset; the clock is still clean.**
  `units_banked` **10 → 15** (+5), `units_this_beat` 7, `units_completed_this_beat` **5**,
  `units_cancelled` 2, `served_units` 0, `terminal: cancelled`,
  `disclosure.reason: served_at_absent`, `units_drifted` 5 (first non-zero of this regime — the
  bank now holds enough carried units to be checkable), `beats_to_publish` 6 (**not an ETA**,
  P181).
- 🆕 **ETA INDEPENDENTLY RE-DERIVED FROM THE LIVE BANK, not inherited.** 15/128 at `10:32Z` at a
  dead-steady +5/beat: completion band 122–127 ⇒ `(122−15)/5 = 21.4` → 22 beats → **`09-02T08:32Z`**;
  full 128 ⇒ 23 beats → **`09-02T09:32Z`**. **`09-02T08:30–09:30Z` STANDS — third independent
  confirmation, and the first one computed on post-repair data.**
- 🟡 **The fence repair (v3970, live `06:54:25Z`) has still moved nothing.** Four post-repair beats
  — `07:31`, `08:31`, `09:34`, `10:32` — all at `units_completed_this_beat: 5`, all cancelling at
  `units_cancelled: 2`. **This is NOT yet the failure verdict:** directive `952` sets that at the
  twelfth post-repair beat (~`18:30Z`), and this is the fourth. Reported as a fact, not a call.
- D-G still open and unanswered ⇒ **freeze holds; this lane deploys no calibration source.**
- **CAL-P186 pushed no code.** There was none to push.
