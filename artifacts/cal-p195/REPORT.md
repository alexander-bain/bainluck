# CAL-P195 — the rebuild is not slow, it is IDLE: 4m42s of work per hour

**Session:** 2026-09-01, ~17:30–18:0xZ / ~10:30–11:0x am PT. Read-only on `app/`. No code changed,
nothing deployed, nothing merged.
**Directive:** Fable-5 RUNNER DIRECTIVE, Tue 2026-09-01 ~10:35 am PT — **the first Fable directive in
six sessions.** ANSWER FIRST, 30 minutes: *can an attended one-off finish the staged rebuild in
hours instead of 26 h of beats, without touching the frozen file's logic?*
**Freeze:** `960` (D-G) in force; ruling 009 freezes `precompute_calibration.py`. Neither is touched
by this session — the answer is a **runtime** change on the deployed slug.
**Self-staged inbox consumed:** `965`.

---

## 0. THE ANSWER — YES, ~4 h INSTEAD OF ~15

Written to `.claude/handoff/alex-inbox/calibration-017-the-rebuild-is-not-slow-it-is-idle-and-you-can-drain-it-today.md`
with the exact command sequence, launch window, verification and abort.

**P195-1 — the 26 hours is the clock, not the query.** The beat is **not budget-limited**: it stops
on `staged:window_stop:units_cancelling` (`STAGED_UNIT_MAX_CANCELLATIONS = 2`) with a quarter of its
window unspent, banks 5 units, and the dyno then **idles 43 minutes** waiting for the next hour.
Calling the identical `_precompute_calibration_main()` back-to-back in one long-lived process is
3.7× faster and changes no logic.

---

## 1. THE MEASUREMENT

`durable_state_snapshots → calibration:main:phase_ledger` (`payload->'stages'`), two consecutive
beats, both read live:

| gauge | 16:32:11Z beat | 17:31:46Z beat |
|---|--:|--:|
| `read:futures_generation` | 24,661 ms | — |
| `read:futures_unit` | 989,822 ms | 958,892 ms |
| `staged:units_completed_this_beat` | 5 | 5 |
| `staged:units_cancelled` | 2 | 2 |
| `staged:unit_ms_mean_completed` | 56,431 ms | — |
| `staged:unit_cancelled_after_ms` | 353,838 / 353,845 ms | — |
| `staged:window_stop:units_cancelling` | present | (same terminal) |
| `staged:units_banked` | 45 | **50** |
| `staged:beats_to_publish` | 4 | **3** |
| `terminal` | cancelled | cancelled |

Phase window = `SOFT_LIMIT_MS 1_500_000 − CLEANUP_MARGIN_MS 120_000` = **1,380,000 ms (23 min)**.
The beat spends **~1,014 s (16.9 min)** of it and stops on the cancellation cap — **`_unit_fits_in_window`
never fires**, which is the same conclusion CAL-P163 reached from the other direction ("a budget you
do not reach is not what is capping you").

### The 17:15Z beat reconstructs to the second

| :15:00 → :15:25 | :15:25 → :20:00 | :20:00 → :31:46 | :31:46 → :15 |
|---|---|---|---|
| freeze the generation, 25 s | **5 real units, 4 min 42 s** (5 × 56.4 s) | 2 units cancel at their 353 s bound, **11 min 46 s** | **idle, 43 min** |

Corroborated independently: the staged **cursor** row's `updated_at` is `17:19:58Z` and **did not
move again** although the beat ran to `17:31:46Z` — cancelled units never write, so the last write
is the last *completed* unit, at exactly the predicted :20.

**Duty cycle: 4 min 42 s of productive work per 60 min = 7.8%.**

* now: **4.77 units/h** (measured over 168 beats, CAL-P183)
* back-to-back: 5 units per 16.5 min = **18 units/h — 3.7×**
* remaining ≈ **72** units (banked 50; real finishes land 122–127, never 128) ⇒ **~14–15 iterations
  ≈ 4 h**

---

## 2. WHY IT IS A RUNTIME CHANGE AND NOT A LOGIC CHANGE

* `_precompute_calibration_main()` takes **no arguments** and needs no Celery context — the task
  wrapper only hands it to `_tracked_run`. A one-off calls the identical function on the identical
  slug.
* **There are no env knobs.** `grep -n "os.environ|getenv"` over `precompute_calibration.py`,
  `calibration_main_build.py` and `calibration_phase_ledger.py` returns **nothing**. Every bound is a
  module constant or a measurement. Runtime is the only lever short of a deploy — which is precisely
  what makes the answer safe under D-G.
* `_main_input_fingerprint()` cannot move, so the bank survives.
* The cursor is written **per unit**, so aborting costs at most the unit in flight.
* The final iteration runs `staged:finalize`, the gate and the publish itself — no separate step.

## 3. THE TWO CONSTRAINTS THAT SHAPE THE COMMAND

**(a) One process, not repeated invocations.** `run_owner()` is `f"{socket.gethostname()}:{os.getpid()}"`
— **stable within a process, new on every `heroku run`.** Each banked unit stamps a lease of
`LEASE_S = HARD_LIMIT_MS/1000 + 300` = **1,860 s**; `decode_staged_cursor_detailed` returns `REFUSE`
when `held_by != owner and lease_expires_at > now`, and `_run_staged_futures` then stands down
(`return None`). So a per-beat `heroku run` loop would refuse *itself* for the first 31 minutes of
every iteration. A `for` loop **inside one process** keeps one owner and never collides.

**(b) A narrow cold-lease launch window.** Last completed unit ~:20 ⇒ lease expires ~:51 ⇒
**launch between :51 and :14 past the hour**. Once the one-off holds the lease, the :15 beat hits the
same `REFUSE` and stands down — the designed anti-corruption path, not a degradation.

**Operational:** `--size=standard-2x` is required (`rss:peak_mb` = **605**; the default one-off is
512 MB). ~5 h ≈ $0.25. The `python3 -u -c 'exec("…")'` form in the inbox file was **executed locally
against a stub before being written** — quoting and syntax both verified under zsh.

## 4. WHAT THIS DOES **NOT** DO

* 🔴 **It does not fix the fence.** 11 min 46 s of every 16.5 min iteration is still two units dying
  at their own bound. If the tail of the roster is only units that cancel, the bank stalls and no
  amount of runtime helps — that is CAL-P190's ratchet. The loop self-stops after two iterations
  with no progress and says so.
* 🔴 **It is not an argument to lift D-G**, and it does not touch the group-key hazard: `category` is
  a data value no digest can see, and running the same code faster changes nothing about it.
* ⚠️ It raises calibration's Postgres duty from 28% to 100% for ~4 h. Each unit keeps its own
  statement timeout (353 s measured), so nothing runs away, but it is the first thing to stop if the
  feed gets slow.

## 5. STATE AT CLOSE

| thing | value |
|---|---|
| fingerprint (live + local predictor) | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 30th session** |
| `origin/master` | **moved** `9eb9e086` → `bcabbf2e`; `git diff --name-only 7d066c50 origin/master \| grep -i calib` **empty, exit 1 — ALL-CLEAR** |
| ledger `updated_at` | `2026-09-01 17:31:46.517193+00:00` — **a new beat, the first since P190** |
| `staged:units_banked` | **50** / 128 (was 45 for five sessions) |
| `staged:beats_to_publish` | **3** (was 4) |
| published curve | `generated_at 2026-08-31T04:37:36Z`, unchanged — 30th session |
| ETA if nothing is done | `09-02T08:30–09:30Z`, not re-derived |
| ETA if the drain runs from 11:00 am PT | **~3:00–4:30 pm PT today** |

**Bus writes:** `alex-inbox/calibration-017-…` (the answer + commands). No `YOUR-TURN.md` edit —
this is a DO for Alex routed through Fable, and Fable owns that file.
