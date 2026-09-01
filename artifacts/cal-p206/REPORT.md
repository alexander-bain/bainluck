# CAL-P206 — the beat-END copy is EIGHT keys, and CAL-P068's premise is backwards

**Session:** 2026-09-01, ~14:3x–15:1x PT. **Directive:** `runner-inbox/calibration/976`.
**Built:** nothing. **Merged:** nothing. **Deployed:** nothing. **Branch moved:** `calibration-190` only.
**`program/calibration-205` @ `293ed0e9` was NOT touched** — `CERT-697` is staged against that SHA.

---

## 0. State check (the three commands, plus both bank rows)

| check | result |
|---|---|
| fingerprint predictor (session START and END) | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, 40th session** |
| **live production `input_fingerprint`** | `e2040f90154fae876f0fb65f5abf74c3` — **equals the local predictor at branch HEAD `293ed0e9`** |
| `origin/master` | `b5c59f38` — **held still for a SIXTH session**, empty diff |
| `/api/calibration` `generated_at` | `2026-08-31T04:37:36Z` — **NOT `2026-09-02`. The freeze binds.** |
| `availability` | `stale`; `temporary_excluded` / `temporary_by_cell` both absent |
| P185 discriminator (datagolf ≠ golf) | **0 rows** — quiescent |
| `TOP-PRODUCT-DEFECTS.md` | 24 items; **no open calibration-lane build item** (12 is lane1's build, 21 lane1's) |
| `CERT-697` | **staged, unclaimed, UNGRADED** — absent from `CODEX-CERT-LOG.md` |

**The drain is moving.** Two-row read (ITEM 1b), both samples this session:

| time | generation | bank (cursor) | ledger copy |
|---|---|---|---|
| 21:21:26Z | `1788297300187` | **70** | — |
| 20:38:56Z (ledger) | `1788293786268` | — | 65 |

Generations DIFFER ⇒ a beat is in flight the ledger has not reported. **Not a stall.**
Bank **65 → 70 / 128**, +5/beat, ~61 min/beat ⇒ **~12 beats to go.**

> 🟢 **Incidental to CERT-697:** the live production `input_fingerprint` written by the running
> dyno equals `_main_input_fingerprint()` at `293ed0e9`. That is **GRADE-THIS #2 satisfied by
> independent measurement** — the certifier still owns the verdict, but the wide digest demonstrably
> did not move. Recorded here so the grader has it; **this is not a self-grade.**

---

## 1. `P206-1` — Q12 on ITEM 2's OWN read-instruction table: the copy class is EIGHT keys, not one

**Question 12:** *"this instruction tells me WHICH ROW to read. Is that where the value is PRODUCED,
or where it is COPIED TO?"* — the question that cost P200–P203 a session each, turned on the table
that records its answer.

`_record_staged_convergence` (`calibration_main_build.py:1396-1429`) performs **exactly one**
`read_snapshot_standalone` (`:1400`). Every gauge below it derives from that single `payload` —
directly, or via `_record_drift_coverage` and `_record_served_bank`, which **take `payload` as a
parameter and never read again**:

| key | line | derivation |
|---|---|---|
| `staged:units_banked` | 1416 | `len(committed)` ← **the one ITEM 2 warns about (P203-1)** |
| `staged:units_drifted` | 1420 | `payload["roster_drift_units"]` |
| `staged:units_drift_checkable` | 1473 | `len(committed) - uncheckable` |
| `staged:units_drift_uncheckable` | 1474 | `committed` + `payload["unit_digests"]` |
| `staged:served_units` | 1515 | `len(payload["served_units"])` |
| `staged:served_drifted` | 1518 | `payload["served_drift_units"]` |
| `staged:served_drift_uncheckable` | 1524 | `served` + `payload["served_digests"]` |
| `staged:served_at` | 1527 | `payload["served_at"]` |

> **ITEM 2's table warns on 1 of these 8 = 12.5% of the population it describes.**

**Why it matters operationally:** ITEM 3 step 1 tells the next session to *"grade a publish on
`served_at` / `served_units`"*. Those are **members of this same family** — beat-END copies with the
same freshness as `units_banked`, whose mid-beat staleness ITEM 2 flags in bold. The table marks the
progress key and leaves the two *grading* keys unmarked.

**Harness:** `artifacts/cal-p206/snapshot_family_coupling.py`, 168 beats, 100% classified.

**What it did NOT show — recorded, not buried:**
* **ARM 3 returned UNTESTABLE.** The failure-coupling claim (all eight vanish together when the read
  fails) is *unconfirmed*: in 168 beats the family was **never wholly absent** (153 whole-present,
  15 partial, 0 absent), so no beat dissociates the two families. The harness refuses the verdict
  rather than asserting it. `STATE_MAX_AGE_S = 14 days` makes a stale refusal very unlikely, which
  is the likely reason.
* **ARM 2 (negative control) held:** `staged:units_partition` is `record_gauge(name,
  STAGED_FUTURES_BUCKETS)` — a module constant emitted from *inside the same try-block* — and is
  correctly **not** in the family. A classifier matching "emitted near the read" would have swallowed it.
* **The 15 partial beats are NOT a defect.** All 15 have `served_units = 0` and no `served_at`. The
  guard is `elif served:` (`:1528`) — an empty served bank emits no `unstamped` complaint, because
  nothing has been promoted to date. Correct by design; the live ledger shows the same shape
  (`served_units = 0`, `served_at` absent). **Checked because an absent gauge with no typed reason is
  gotcha #53; this one is intended.**

**Severity: OPERATOR-only, LOW.** No wrong published number. The instrument is *fresh when written*
and stale for the ~61 minutes until the next beat rewrites it — exactly P203-1, now generalised from
one key to eight. **The finding is the table's coverage, not a code defect.**

---

## 2. `P206-2` — Q5 on CAL-P068: the fix is ENGAGED, and its stated premise has the sign backwards

**Question 5:** *"this thing was FIXED. Is the fix CONNECTED to the thing it fixed?"* — 3-for-3
before this session. Tell that fired: a CAL-NNN comment block arguing a bias *direction*.

`_record_staged_rate` (`:1592-1628`) projects:

```
per_beat         = usable_ms / projection_mean
beats_to_publish = ceil((BUCKETS - banked) / per_beat)
```

CAL-P068 changed `projection_mean` from `unit_ms_mean` (all TIMED units) to
`unit_ms_mean_completed` (COMPLETED only). Its comment (`:1608-1613`) states the reason:

> *"A beat runs N units and the last is cancelled at the deadline, so the truncated observation drags
> the mean **DOWN**; a lower mean means more units appear to fit per beat, which means FEWER beats
> appear to remain. The projection was optimistic by construction."*

**The fix is engaged.** Live ledger carries `staged:beats_basis:completed`.

**The premise is false, measured two independent ways:**

1. **Live decomposition (2026-09-01 21:2xZ, one beat, exact):** `ran=7, completed=5, cancelled=2`,
   mixed mean `186,306 ms`, completed mean `77,940 ms`. Implied cancelled mean =
   `(7×186,306 − 5×77,940) / 2` = **457,221 ms — 5.9× LARGER than a completed unit**, not truncated-smaller.
2. **168-beat ring:** beats with ≥1 cancellation have a median `unit_ms_mean` of **161,688 ms**
   vs **140,875 ms** without — cancellations **RAISE** the mean by **1.15×** (n=16 vs 149).

Cancelled units are not truncated short; they run **to the fence** and bank nothing.

**Consequence — the fix moved the number the wrong way.** Since `completed_mean < mixed_mean`, the
swap can only *raise* `per_beat` and *lower* `beats_to_publish`. Live:

| basis | per_beat | `beats_to_publish` |
|---|--:|--:|
| completed mean 77,940 ms (**current, post-CAL-P068**) | 17.71 | **4** ← matches production exactly |
| mixed mean 186,306 ms (pre-CAL-P068) | 7.41 | 9 |
| **measured throughput (5 banked/beat)** | 5.00 | **13** |

The beat is **94.5% busy**, not idle: 7 units consume `1,304,142 ms` of a `1,380,000 ms` window, and
**914,442 ms of that is burned on the 2 units that banked nothing.** `beats_to_publish` is a
*throughput* projection, so that wasted time must be charged to the units that did bank. The mixed
mean happened to absorb it; the completed mean excludes it by construction.

**Measured bias of the PRE-fix arm** (`artifacts/cal-p206/beats_to_publish_bias.py`, 168 beats,
**90.5% classified**, ARM 1 reproduction consistent 157 / inconsistent 8, ARM 2 confirms the ring is
wholly on the mixed basis):

> **median projected/actual = 1.30× optimistic; optimistic on 137/152 beats (90.1%); range 0.81×–9.25×.**

So the projection was *already* optimistic on the basis CAL-P068 replaced, and the replacement pushes
it further the same way. This is the mechanism behind P198-1's symptom (`beats_to_publish` rose 3→5
while the bank rose 55→60) and behind ITEM 2's standing "**beats remaining ⇒ read NOTHING**" rule —
the conveyor had the right instruction and not the reason.

**Honest limits — stated, not buried:**
* The 168-beat population measures the **PRE-fix** arm. The post-fix magnitude (3.2× at
  `btp=4` vs ~13) rests on **one live beat** plus the monotonicity argument. **It is not a population
  result and must not be quoted as one.**
* ARM 1 found 8 beats where published `btp` fell *below* the full-window lower bound. The ring does
  not carry `fixed_ms`, so those 8 are unexplained rather than contradictory; the harness reports
  them rather than dropping them.
* n=16 for the cancellation arm — suggestive alone; it is the live decomposition (unambiguous within
  a single beat) that establishes the sign.

**Severity: OPERATOR-only.** `beats_to_publish` is not user-visible and appears nowhere in
`/api/calibration`. No wrong published number.

---

## 3. What I did NOT do, and why

🔴 **I did not fix either finding.** `980` clause 6 forbids a build lane queueing instruments or
guards on their own account, and ruling 134 puts diagnosis in the measurement lane. Both findings are
OPERATOR-facing gauges. **A one-line change to `projection_mean` is exactly the tempting wrong move**
— it is a fold's call, and correcting a throughput denominator without re-deriving the fence model
(ITEM 2) would be the third guess at this number, not the last.

🔴 **I did not touch `program/calibration-205`.** `CERT-697` is staged against `293ed0e9`; committing
artifacts there would have moved the graded subject out from under the cert bus.

🔴 **I did not merge or push anything that releases.** Curve reads `2026-08-31`; the freeze binds
until `2026-09-02`.

🔴 **I did not open a third branch.** WIP limit is 2. Artifacts went to `calibration-190`, which
ITEM 1 names as the artifact/test branch.

🔴 **I did not add to `TOP-PRODUCT-DEFECTS.md`.** Build lanes do not add items, and neither finding is
user-visible.

---

## 4. Parked (bus writes)

* **`P206-1`** — the beat-END copy class is 8 keys; ITEM 2's table covers 12.5% of it, and the two
  keys ITEM 3 names for *grading a publish* (`served_at`, `served_units`) are unmarked members.
  Coupling-on-failure UNTESTABLE on 168 beats.
* **`P206-2`** — CAL-P068 is engaged and its premise is inverted; cancelled units are 5.9× larger than
  completed, not truncated smaller, so the fix lowers an already-optimistic projection. Pre-fix arm
  measured 1.30× optimistic over 152 beats.

Both OPERATOR-visible. Neither belongs on `TOP-PRODUCT-DEFECTS.md`. Neither is a near-miss on the
ITEM 6 group-key hazard — that hazard is about **roster COLUMNS the digest cannot see**; these are
about **ledger gauge freshness and a projection denominator**. Do not let either be read as closing it.

---

## 5. Artifacts

| file | what |
|---|---|
| `snapshot_family_coupling.py` | Q12 harness, 4 control arms, 168 beats, 100% classified |
| `beats_to_publish_bias.py` | Q5 harness, 4 control arms, 168 beats, 90.5% classified |

Both carry the counterfactual arm and **both refused a verdict at least once during this session** —
`snapshot_family_coupling` still reports UNTESTABLE, and `beats_to_publish_bias` reported
`0/168 classified` until a wrong rebuild-boundary test was corrected. **`generation` in the ring is
stamped PER BEAT (168 distinct values over 168 beats), not per rebuild** — group on `banked`
decreasing instead. That trap is worth carrying forward.
