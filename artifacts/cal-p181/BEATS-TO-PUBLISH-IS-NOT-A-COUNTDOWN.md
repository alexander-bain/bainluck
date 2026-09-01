# CAL-P181 — the ETA instrument lies, and the freeze is cheaper than we told Alex

**2026-09-01 ~09:05Z / ~02:05 am PT.** Source: one `GET /api/admin/calibration-beat-gauges?full=true`
(`artifact_generated_at 2026-09-01T08:45:21Z` — **unrefreshed since CAL-P180 read it**, trap 8).
168 observations, `2026-08-25T08:35Z → 2026-09-01T08:31Z`. No new instrument was fetched, no code
was written, nothing was deployed. Everything below is a re-read of the history P178–P180 already had.

---

## 0. THE HEADLINE

**D-G's freeze costs ~17 hours, not ~26.** The `~26 h` figure on `YOUR-TURN.md` and on #2052 was
extrapolated from the *slowest run ever observed* — which is also the run that got killed. Measured
across all **seven completed cycles**, the rebuild takes **12.9–23.2 h, median 16.1 h, mean 17.4 h**.

**And the gauge everyone has been reading as the ETA is not an ETA.** `staged:beats_to_publish`
matches the actual beats-until-publish **9 times in 137 (13%)**. It floors at `1` and prints `1`
for up to three consecutive beats.

---

## 1. `staged:beats_to_publish` IS NOT A COUNTDOWN TO PUBLISH

Tested against what actually happened next, over the whole window:

| tested against | exact | within ±1 | mean error |
|---|---|---|---|
| beats until the page next **published** | **9/137 = 13%** | 18/137 = 13% | **+4.95** |
| beats until the **bank completed** | 27/124 = 22% | 55/124 = 44% | −1.59 |

It is not a countdown to publish, and it is only a mediocre countdown to completion. Two specific
failure modes, both of which have already misled a session:

- **It floors at 1.** Worked example from the 08-30 cycle: it printed `1` at bank 114 (3 beats
  remained), `1` at bank 124 (2 remained), `1` at bank 126 (1 remained). *"It printed 1 for three
  straight beats"* means **"≥1 beat remains"** — it does not mean the run was one beat from done.
- **Most `actual` values are 0** — i.e. the beat reading `beats_to_publish: 5` **published on that
  very beat**. Publishes happened at bank 18, 24, 29, 122, 0, 13… every level. This independently
  re-confirms P178: **the bank was never the publish trigger**, and a gauge named
  `beats_to_publish` that keys on the bank cannot be measuring publication.

🔴 **Consequence for the record:** CAL-P180's sharpest claim — *"the killed run's own gauge printed
`beats_to_publish: 1` for three straight beats"* — is **not valid evidence**. The **conclusion still
holds**, but on different evidence: bank **119** against empirically measured completion peaks of
**122–127** ⇒ the run was **1–2 beats** from done. Cite the peaks, never the gauge.

---

## 2. THE REBUILD IS FASTER THAN RECORDED — ALL SEVEN COMPLETED CYCLES

Beat cadence is a clean **60.0 min median** (hourly), so *beats ≈ hours*.

| cycle | start | peak | hours | units/h | verdict |
|--:|---|--:|--:|--:|---|
| 0 | 08-25 08:35 | 94 | 9.0 | 8.45 | **WIPED** (deploy) |
| 1 | 08-25 18:32 | 123 | 14.1 | 8.14 | completed |
| 2 | 08-26 09:27 | 122 | 16.1 | 7.56 | completed |
| 3 | 08-27 02:33 | 123 | 17.0 | 7.22 | completed |
| 4 | 08-27 20:28 | 124 | 23.2 | 5.35 | completed |
| 5 | 08-28 20:37 | 127 | 23.0 | 5.53 | completed |
| 6 | 08-29 20:21 | 122 | 15.3 | 7.98 | completed |
| 7 | 08-30 12:25 | 126 | 12.9 | 9.76 | completed |
| 8 | 08-31 02:19 | 36 | 3.3 | 10.91 | **WIPED** (deploy) |
| 9 | 08-31 06:37 | 119 | 23.9 | **4.77** | **WIPED** (deploy) |
| 10 | 09-01 08:31 | 5 | — | — | **IN FLIGHT** |

**Completed: mean 17.4 h · median 16.1 h · range 12.9–23.2 h · rate 5.35–9.76 u/h.**

Cycle 9 — the one killed this morning — ran at **4.77 u/h, the slowest rate anywhere in the
window**. `~26 h` is that single worst case projected to 124 units. It is a defensible *ceiling*,
but it was recorded as *the* number.

### Corrected ETA for the live run (started `08:31:38Z`, bank 5, target ~124)

| basis | completes |
|---|---|
| fastest completed cycle (12.9 h) | `09-01T21:25Z` |
| **median completed (16.1 h)** | **`09-02T00:37Z`** |
| **mean completed (17.4 h)** | **`09-02T01:55Z`** |
| slowest completed (23.2 h) | `09-02T07:43Z` |
| slowest ever, the killed run (26.0 h) | `09-02T10:31Z` |

**Expected `09-02T00:30–02:00Z`; plan against `09-02T08:00Z` as the ceiling.** The handoff's
`09-02T08–10Z` is the pessimistic tail, **6–9 h late** on the central estimate. A fresh curve is
plausible **tonight**, not tomorrow morning.

⚠️ Publish is decoupled from the bank, so *publication* is completion **+ ~1 beat** (the beat that
sees the freshly installed artifact and finds `served_at` present).

---

## 3. 🔴 THERE WERE **FOUR** DEPLOYS IN THE WINDOW, NOT THREE

P180 counted wipes by looking for a **bank drop under a changed fingerprint**. That misses one:

| when | fingerprint | bank | detectable as a drop? |
|---|---|---|---|
| 08-25 18:32 | `b65faaac → b1820040` | 94 → 8 | yes |
| 08-31 06:37 | `b1820040 → 75faaed6` | 36 → 5 | yes |
| 09-01 07:31 | `75faaed6 → af47b8e0` | 119 → 5 | yes |
| **09-01 08:31** | **`af47b8e0 → e2040f90`** | **5 → 5** | 🔴 **NO — the bank did not fall** |

The fourth deploy landed while the bank was already at 5, so it wiped a one-hour-old run and left
**no drop to detect**. (It is real: it is the second of the two wipes "62 minutes apart" that D-G
already describes — the RULE E merge.)

**Rule to carry:** *count wipes by `input_fingerprint` change, never by a bank drop.* A drop is
neither necessary (this row) nor sufficient (seven of the ten drops are completions) for a wipe.

---

## 4. NEGATIVE RESULT — no live-ETA formula from `unit_ms_mean`

I checked whether `staged:unit_ms_mean` predicts `staged:units_completed_this_beat`, which would
give a self-updating ETA. It does not, and the sign is backwards from intuition:
`unit_ms_mean < 90 s` → **6.00** completed/beat (n=10); `≥ 90 s` → **7.06** completed/beat (n=154).
No usable signal. **The honest ETA remains the empirical cycle-duration distribution in §2** — there
is no cheaper instrument, so do not go looking for one.

---

## 5. WHAT THIS DOES AND DOES NOT CHANGE

**Unchanged (do not re-derive):** the root cause (#2052's 22.5-min statement-timeout wall);
`served_at_absent` is what blocks the page; `staged:served_*` and `units_banked` are independent;
the two dead hypotheses (drift, staleness). The rebuild still completes on its own — **7 times in
5 days**, exactly as P180 said.

**Changed:** the freeze is **~17 h expected / ~23 h worst completed**, not ~26 h — so **D-G option
(a) is cheaper than Alex was told**, and the case for it is correspondingly stronger.
`beats_to_publish` must not be quoted as an ETA by anyone again. Wipes are counted by fingerprint.

**Still true and still the only thing that matters:** *nobody deploys
`backend/app/tasks/precompute_calibration.py`.* The predictor at HEAD returns
`e2040f90154fae876f0fb65f5abf74c3`, matching the live beat — **no reset is baked in.**
