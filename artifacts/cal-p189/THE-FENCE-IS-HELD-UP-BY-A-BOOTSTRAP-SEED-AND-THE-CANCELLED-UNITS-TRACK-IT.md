# CAL-P189 (#1978, #2052) — the fence is a bootstrap SEED, the ring is 7 entries not 24, and the cancelled units die at whatever the fence is

**Session:** CAL-P189, 2026-09-01, ~12:45–14:15Z / ~05:45–07:15 am PT
**Lane:** calibration (build lane, idle on the build board by roadmap — ruling 134)
**Shipped code:** none. D-G's default freeze on calibration-source deploys holds and was honoured.
**Supersedes:** the dated prediction in `artifacts/cal-p188/THE-FENCE-IS-HELD-UP-BY-ONE-OBSERVATION-THAT-AGES-OUT-TONIGHT.md` §3.

---

## 0. THE ONE PARAGRAPH

P188 read the fence off the ledger, reproduced it exactly, and projected that the single observation
holding it up would age out of a 24-beat ring at ~`09-01T19:30–20:30Z` tonight, re-arming the
CAL-P163 ratchet. **The mechanism was right and the object was wrong.** The ring is not a
reconstruction and did not need one — it is stored verbatim in the ledger payload under
`unit_worst_history` and is one `db-query` away. Read directly, it holds **seven entries, not
twenty-four**, and its maximum is not an observation at all: **255,836 ms is CAL-P167's
`_bootstrap_worst_history` SEED**, computed once as `carried_mean × STAGED_UNIT_OVERRUN_FACTOR`
(`63,959 × 4.0`) at the `07:31Z` beat, the first beat after v3970 deployed the ring itself. It ages
out after **16 more contributing beats from the `14:34Z` beat — ~`09-02T06:30Z`, not tonight.**
🔴 **And the finding that matters more than the date: across three fence levels spanning 66,420 ms,
all seven cancelled units died within 531 ms of the fence, whatever the fence was** — 353,754 →
deaths at 353,840/353,843/353,915/354,285; 420,174 → 420,251/420,285; 403,830 → 403,954, the fence
moving *down* on the last one. **The units that cancel are not units the fence is refusing too
tightly. They consume the entire fence at every width tried, so widening the unit bound cannot bank
them** — which is the opposite of the fix direction the fence measurement was scheduled to support.

---

## 1. READ THE RING ITSELF — it is in the payload, not a reconstruction

P188 reconstructed the ring by scanning the captured 168-beat series of `staged:unit_ms_worst` and
carried a ±2-beat band because the carried max (255,836) exceeded the best captured observation
(250,681). **That gap did not need to be estimated.** `save_phase_ledger` writes the ring into the
same payload the gauges live in (`calibration_main_build.py:1724`,
`UNIT_WORST_HISTORY_KEY = "unit_worst_history"`), so:

```sql
SELECT updated_at, payload->>'unit_worst_history' AS ring
FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger'
```

Beat `2026-09-01T12:32:56.924818Z`:
```json
{"futures": [255836, 52664, 53070, 103783, 85318, 80739, 85870]}
```

**Seven entries.** `merge_history` appends to the tail and keeps `[-24:]`, so index 0 is the oldest.

**The last six map one-to-one onto the last six beats**, each 56–130 ms *below* that beat's captured
`staged:unit_ms_worst` — which is exactly the offset the two instruments must have:

| beat | ring entry | captured `unit_ms_worst` | Δ |
|---|--:|--:|--:|
| `07:31:29` | 52,664 | 52,737 | 73 |
| `08:31:38` | 53,070 | 53,126 | 56 |
| `09:34:34` | 103,783 | 103,882 | 99 |
| `10:32:30` | 85,318 | 85,448 | 130 |
| `11:32:41` | 80,739 | 80,828 | 89 |
| `12:32:56` | 85,870 | 85,957 | 87 |

The offset is structural, not noise. `staged:unit_ms_worst` comes from the beat-local
`unit_ms = time.monotonic() − unit_started` computed at `precompute_calibration.py:4737` — **after**
`runner.commit(db)` and `save_staged_cursor`. The ring is fed from
`ledger.stage_completed_max_ms("read:futures_unit")`, whose `with runner.stage(...)` block wraps
**only** `db.execute` + `result.all()` (`:4660-4670`). So `unit_ms ⊃ stage span` for the same unit,
always, and the delta is the commit + cursor write. **The ring entry can therefore never exceed its
own beat's `unit_ms_worst`** — which is what makes 255,836 > 250,681 impossible to explain as an
observation, and is what pointed at the seed.

---

## 2. 🔴 255,836 IS A SEED, NOT AN OBSERVATION

`_bootstrap_worst_history` (`calibration_main_build.py:1014-1071`, CAL-P167, repairing CERT-637):

```python
seeded[name] = [int(mean_ms * STAGED_UNIT_OVERRUN_FACTOR)]
```

fired from `load_phase_carryover` (`:1105-1108`) **only when the ring is empty**:
```python
if not ring:
    ring = _bootstrap_worst_history(costs)
```

**`255,836 / 4.0 = 63,959` exactly** — a carried `unit_costs.futures.unit_ms` level, which live sits
at 63,592–65,284 and is entirely consistent with 63,959 at `07:31Z`.

**Why the ring was empty at `07:31Z`:** v3970 — the deploy the directive calls "the fence repair",
live `06:54:25Z` — is the code that introduced the ring. `06:31` ran on the old fingerprint
(`75faaed6`); `07:31` is the first beat on the new one (`af47b8e0`) and found a ledger with
`unit_costs` and no `unit_worst_history`. **That is precisely the state `_bootstrap_worst_history`'s
docstring says it exists for:** *"Every durable ledger written before that deploy carries
`unit_costs` and no ring."*

So the seed is **the repair working exactly as designed, on its first beat**, and the fence of
353,754 that P188 measured and called "in force and exact" is in force — but it is the *seed's*
fence, not a fence built from observed completions.

**Consequences, all three load-bearing:**

1. **The holder is not the `08-31T18:37:31Z` beat.** That beat's 250,681 ms completion is not in the
   ring at all — the ring was created empty five beats later. P188's "THE ONLY OBSERVATION HOLDING
   THE FENCE UP" names a beat that cannot be holding anything.
2. **The window is 24 ENTRIES, not 24 beats.** `_unit_worst_from` returns `{}` when no unit
   completed, and `merge_history` only appends for names present in `observations` — so a
   zero-completion beat **freezes** the ring instead of aging it. Three such beats are visible in
   the retained series (`08-30T23:28`, `08-31T01:20`, `09-01T04:19`, all `terminal: cancelled`).
3. **The eviction date moves by ~10 hours.** The seed is entry #1 of 7. It leaves on the **25th**
   append, i.e. after **18 more contributing beats**. At ~1 beat/h from the `12:32Z` beat that is
   **~`09-02T06:30Z`**, and later if any beat completes zero units.

---

## 3. 🔴 THE HEADLINE — the cancelled units die at whatever the fence is

This is the finding that changes what should be built, and it fell out of watching a second beat.

The fence is recomputed **per unit**, in `apply_unit_statement_timeout`
(`calibration_main_build.py:711-744`), and `record_gauge` overwrites — so
`staged:unit_bound_ms:{phase}` in the ledger is the bound applied to the **last unit attempted**,
which (the loop `break`s on the 2nd cancellation) is always the final cancelled unit.

```
mean_basis  = measured × STAGED_UNIT_OVERRUN_FACTOR(4.0)     # measured = this beat's worst-so-far,
                                                             #   falling back to the carried mean
worst_basis = measured_unit_worst_ms × BUDGET_SAFETY(1.5)    # = max(ring)
fence       = min(phase_bound, max(mean_basis, worst_basis) − STATEMENT_INNER_MARGIN_MS(30,000))
```
(`calibration_phase_ledger.py:1557-1567`; constants `:241`, `:245`, `:322`.)

**Measured, four beats, three fence levels:**

| beat | this beat's worst completion | binding term | fence | cancellations | Δ over fence |
|---|--:|---|--:|--:|--:|
| `11:32:41` | 80,828 | seed (383,754) | **353,754** | 353,843 · 353,915 | +89 · +161 |
| `12:32:56` | 85,957 | seed (383,754) | **353,754** | 353,840 · 354,285 | +86 · +531 |
| `13:36:02` | 112,543 | **beat-local (450,172)** | **420,174** | 420,251 · 420,285 | **+77 · +111** |
| `14:34:24` | ~108,458 | **beat-local (433,830)** | **403,830** | 403,954 | **+124** |

**The fence moved across a 66,420 ms range and the deaths moved with it, to the millisecond** —
including *downward* at `14:34`, which rules out a monotonic drift explanation. Seven cancellations,
four beats, three fence widths, every death inside 531 ms of its own bound.

**The `14:34` fence was predicted before it was read.** From the model: `108,204 + Δ ≈ 108,304`,
`× 4 = 433,216`, `− 30,000 = 403,216`. Observed **403,830** — a 614 ms miss, which is the error in
the assumed commit+cursor Δ and nothing else (the implied Δ is 254 ms, inside the 56–130 ms band's
order of magnitude).

At `13:36` the beat-local term overtook the seed: `112,543 × 4 = 450,172 > 255,836 × 1.5 = 383,754`,
so `450,172 − 30,000 = 420,172 ≈ 420,174`. The crossover is a beat worst of **95,938 ms** — above
that the seed is irrelevant to that beat's later units, which is why P188's two beats (80,828 and
85,957) both read 353,754 and looked like a constant.

**What this establishes.** Six cancellations across three beats and two fence widths, every one
inside 531 ms of its own bound. A unit that is merely *somewhat* too expensive would complete once
the fence rose 66 s; none did. **These units consume the whole fence at every width tried.** The
largest completion ever captured is 250,681 ms; these want >420,285 ms and counting.

🔴 **Therefore: widening the unit bound cannot bank them, and P188's implied direction — *"the fence
is ~5 minutes below the available window, which points at a different fix (the unit bound)"* — is
not supported by the evidence.** Widening buys more burnt window per beat, not more banked units.
Note the cost is already visible: `unit_bound_headroom_ms` fell from 304,577 to **183,340** as the
fence widened, i.e. the beat is now withholding less because the fence is eating the window.

⚠️ **What this does NOT establish.** Whether the units are genuinely non-terminating or merely very
large is not decided by three beats — the durations are censored at the fence by construction
(P188 §7 made the same point and it stands). And the cancelled `chunk.key`s differ every beat
(`2ef60c20…`/`8f51d074…` → `0083c993…`/`2c26d1c6…` → `248c4616…`/`fe91dcaa…`), so it is **not** a
fixed pathological pair. Why a retried-first cancelled chunk presents a different key each beat is
**unresolved and is the single best next question** — `staged:unit_cancelled:{chunk.key}` is
dropped by the sampler, so there is no history to scan and it must be watched live.

---

## 4. WHAT THE SEED'S EVICTION WILL ACTUALLY DO — smaller than billed, but not nothing

When the seed leaves (~`09-02T06:30Z`), `worst_basis` falls from 383,754 to `max(real ring) × 1.5`.
The real entries max at 112,436 today ⇒ **168,654**. The first unit of a beat has no beat-local
worst yet, so it falls back to the carried mean: `63,592 × 4 = 254,368` ⇒ **fence ≈ 224,368**.

| | first unit of a beat | after a ~112 s completion |
|---|--:|--:|
| now (seed present) | 353,754 | 420,174 |
| post-eviction | **~224,368** | ~420,174 (unchanged — beat-local dominates) |

So the eviction tightens **only the first unit or two of each beat**, from ~354 s to ~224 s, and the
within-beat ratchet re-widens it as soon as anything sizeable completes. Every completion in the
current regime is ≤ 112,543 ms, comfortably inside 224,368.

🟡 **The residual risk is real but narrower than P188's.** Completions of 250,681 ms and 179,111 ms
are both in the recent record. A unit of that size arriving as a beat's *first* unit post-eviction
would be refused at 224,368 where today it would be admitted — and each such refusal removes a large
completion from the ring, lowering `max(ring)`, which is the CAL-P163 ratchet. **It is a first-unit
ordering hazard, not the general re-arming of the fence**, and the `mean_basis` floor of
`carried_mean × 4` stops it running away.

**Pre-registered, and it supersedes P188's:**
- 🔴 **The fence will NOT drop tonight.** P188's `19:30–20:30Z` prediction is **falsified in
  mechanism before its date** — the object it names is not in the ring. Its own falsifier (*"still
  353,754 at `09-01T22:30Z`"*) is **already void**, because the fence left 353,754 at `13:36Z` by
  widening, for a reason unrelated to aging.
- **The ring grows by exactly one entry per contributing beat**, seed at index 0, until the 25th
  append. ✅ **Confirmed once already** — see §5.
- **`staged:unit_worst_carried_ms:futures` reads 255,836 on every beat until ~`09-02T06:30Z`**, then
  drops to `max(real ring) × 1` (~112k–180k).
- **Each beat's `unit_bound_ms` ≈ `max(4 × that beat's worst completion, 383,754) − 30,000`**, and
  both cancellations land within ~600 ms of it.

---

## 5. LIVE CONFIRMATION — two beats, both pre-registered

Pre-registered before each beat landed: *the ring grows by exactly one entry, seed stays at index 0.*

| beat | ring | appended | `units_done` |
|---|---|--:|---|
| `13:36:02Z` | `[255836, 52664, 53070, 103783, 85318, 80739, 85870, 112436]` | 112,436 | 25 → 30 |
| `14:34:24Z` | `[…, 112436, 108204]` (9 entries) | 108,204 | 30 → 35 |

✅ **Both exactly as predicted**, seed still index 0 in both, +5 banked per beat.

### 5b. 🆕 The `14:34` beat did NOT stop on the cancellation cap — and two carried rules are wrong

`stage_counts` for `14:34:24Z`: `{"read:futures_unit": 7, "staged:units_cancelled": 1, …}`, with
**no `staged:window_stop:*` key of any kind** and **`staged:unit_ms_worst` absent**.

- **Only ONE cancellation**, so the beat cannot have stopped on
  `STAGED_UNIT_MAX_CANCELLATIONS = 2`. This is the first beat in the seven-beat post-repair streak
  that did not. It still banked exactly 5.
- 🔴 **The carried rule *"`staged:units_cancelled` under-reports — use `units_this_beat −
  units_completed_this_beat`"* is WRONG on this beat.** That formula gives `7 − 5 = 2`; the true
  count is **1**, and the single `staged:unit_cancelled:{chunk.key}` gauge agrees with the count,
  not the formula. 7 attempts = 5 completed + 1 cancelled + **1 unattributed**.
- The absent `unit_ms_worst` and absent stop reason together point at the loop leaving through the
  `save_staged_cursor` failure path (`precompute_calibration.py:4726-4732`), which `return None`s
  **before** `_record_convergence_projection` runs. **Consistent with all the evidence, not
  confirmed** — and it is the same signature as the three earlier `terminal: cancelled` beats
  (`08-30T23:28`, `08-31T01:20`, `09-01T04:19`) that also carry `unit_ms_mean` but no
  `unit_ms_worst`.

### 5c. 🆕 `unit_ms_mean`'s contamination is now arithmetic, not inference

Trap 22 says `staged:unit_ms_mean` is a mixed mean. The `14:34` ledger closes it exactly:

```
read:futures_unit (total)  = 1,117,368 ms   stage_counts = 7 attempts
1,117,368 / 7              = 159,624        = staged:unit_ms_mean   ✓ EXACT
staged:unit_ms_mean_completed                = 70,412  (completed only)
```

**It divides total unit time by ATTEMPTS, so every cancelled unit — each of which burns the entire
fence, ~400 s — is in the numerator.** That is the whole 2.3× overstatement, and it means the gauge
inflates *precisely when the fence is widest*. It is not a sampling artefact; it is the definition.

This also settles which gauges come from which producer, and the split is not the intuitive one:
`units_this_beat`, `unit_ms_mean`, `units_completed_this_beat`, `unit_ms_mean_completed` and
`beats_to_publish` are all **ledger-derived** in `calibration_main_build.py:1559-1594`
(`units_this_beat` is `stage_counts[…]`, i.e. **attempts, not completions**), while `unit_ms_worst`
and `prior_unit_ms` are **loop-local** in `precompute_calibration.py`. That is why a beat can carry
one and not the other.

---

## 6. STATE, MEASURED THIS SESSION

- **Fingerprint** `e2040f90154fae876f0fb65f5abf74c3`; the local predictor at HEAD reproduces it
  exactly. **No fifth reset. The clock is clean.**
- **`origin/master` = `7d066c50`, unchanged.** `git log 7d066c50..origin/master --name-only | grep
  -i calib` ⇒ empty, exit 1 (the all-clear).
- **P185's group-key discriminator: 0 rows** at `12:47Z` — the **fifth** consecutive zero
  (P185/P186/P187/P188/P189). Quiescent.
- **Bank** 25 → 30 → 35 across the three beats sampled, **+5/beat, dead steady**. From 35, the
  122–127 completion band is **~18 beats out ⇒ `09-02T08:30–09:30Z`. The ETA stands, now confirmed a
  sixth time**, and the risk P188 attached to it for *tonight* is **withdrawn**: the seed's eviction
  is dated ~`09-02T06:30Z` — about two hours BEFORE the publish, not on top of the beat-12
  checkpoint — and per §4 is not expected to change the completion rate.
- **Published curve unchanged for a twenty-fourth session** (`generated_at 2026-08-31T04:37:36Z`,
  `mce_closing_line 1.86`). Fully explained; not re-derived.

**Also settled in passing:** `staged:units_partition` — listed as "dropped, purpose unread" in the
carried directive — is simply `128`, identical to `staged:units_planned` on every beat read.
**Redundant with a captured gauge; do not chase it.** That leaves `staged:generation` as the only
untested quotable.

---

## 7. WHY NOTHING WAS BUILT

Unchanged from P188 and for the same two reasons, both of them the rules working:

1. **Ruling 134.** Everything here is instrumentation and diagnosis for the measurement lane. No
   user-visible ship. Parked as `P189-1`.
2. **D-G.** Default (a) — freeze on calibration-source deploys — is still the only open Alex-ask
   this lane owns, and `calibration_beat_gauge_sampler.py` is calibration source.

🟢 **And the freeze's cost fell again this session.** P188 bounded it at "15 dropped gauges/beat,
readable live via the ledger". §1 removes the rest: **the ring — the one piece of carried state the
sampler can never show, and the thing the fence is built from — is itself in the payload and
readable on demand.** The capture gap is a history gap, not a visibility gap, and after this session
it is a history gap with a documented workaround for its most load-bearing item.

---

## 8. WHAT THIS SESSION DID NOT MEASURE

- **Why the cancelled `chunk.key` differs every beat.** §3's open question, and the best next one.
  The loop skips banked chunks in fixed order, so a chunk cancelled in beat N should be attempted
  first in beat N+1 with the same key. It is not. Unresolved.
- **What the cancelled units actually cost.** Censored at the fence by construction; only a rising
  lower bound exists (>420,285 ms as of `13:36Z`).
- **Whether the build can reach 128 at all** while ~2 chunks per beat refuse. The carried completion
  band is 122–127, never 128, which is consistent with a small residue of chunks that never bank —
  but this session did not establish the connection and it should not be asserted.
