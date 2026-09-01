# CAL-P196 — the two drift twins measure over different intervals, and the freshness gate can never close

**Session:** 2026-09-01, ~17:40–18:15Z / ~10:40–11:15 am PT. Directive `966`.
**Lane state:** D-G freeze in force. Nothing built. Nothing deployed. Nothing merged.
**Pillar:** TRUTH. **Nothing here is a ship** — three parks, `P196-1/2/3`, for a fold.

---

## 0. Session preamble (the two mandatory commands, plus the ledger)

| check | result |
|---|---|
| `_main_input_fingerprint()` | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, THIRTY-FIRST session** |
| `origin/master` | `bcabbf2e…` — **did not move** from `965`/`966`'s reading |
| `git diff --name-only 7d066c50 origin/master \| grep -i calib` | **empty, exit 1 — ALL-CLEAR** |
| published curve `generated_at` | `2026-08-31T04:37:36Z` — **unchanged, THIRTY-FIRST session** |
| ledger `updated_at` | `2026-09-01T17:31:46.517193Z` — **unmoved since P195 read it** |
| publish / drain | **neither**. `served_units 0`, `served_at` absent, `terminal cancelled` |

**No publish ⇒ `ITEM 3 step 3` did not trigger**, and P185's discriminator was correctly not run
(it is a pre-grading check, and there is nothing to grade). Both ship predictions stay ungraded.

The beat did **not** move this session: `units_banked` 50, `beats_to_publish` 3, identical to
`965`'s reading 9 minutes before session start. **ETA `09-02T08:30–09:30Z` stands, not re-derived.**

---

## 1. The question, and why this one

`966` ITEM 6 flagged `staged:units_drifted` as **"a number nobody has explained… Unexamined; do not
quote it."** It read 34-of-40 at P191 and **39-of-45** now. That is the only live gauge on the board
carrying an unexplained value, so it got question 1 — ***"what, exactly, does this guard compare —
and what is therefore NOT in it?"*** — aimed at it, in P194's RUNTIME-guard extension.

It paid, and then question 7 (***"the docstring and the guard disagree — which does the CALLER
believe?"***) paid on top of it.

**Both proofs run from anywhere and exit 0:**
`artifacts/cal-p196/drift_semantics.py` (source containment, 12 checks) and
`artifacts/cal-p196/ring_reachability.py` (168 captured production beats). Outputs committed beside
them. The ring is **CAL-P118's artifact, reused, not re-collected** — `966` ITEM 3 q2's rule.

---

## 2. `P196-1` — `roster_drift`'s docstring is falsified by its only caller

`roster_drift` (`calibration_staged_futures.py:2062`) says, twice:

> How many BANKED units the roster has moved under **since they were banked**. […] the plan's current
> membership digest for its slot differs from the digest stored **when the unit ran**.

Its **only** caller is `retain_planned_units` (`:1946`, invoked once per beat from
`precompute_calibration.py:4594`). That function's unconditional tail is:

```python
:2054   unit_digests={name: digests[name] for name in kept if name in digests},
```

**Every kept unit is re-stamped to the CURRENT plan, every beat, with no "only if missing" guard.**
So the digest `roster_drift` compares against is **last beat's**, never "when the unit ran".

⇒ **`staged:units_drifted` is a PER-BEAT DELTA (~1 hour), not a cumulative count.**

`retain_planned_units` is itself honest about this — *"measure, then re-stamp… Re-stamping first
would make every beat report zero drift forever"*. The defect is that the function whose **name and
docstring** the consumers read describes the other thing.

### The twin does the opposite, and is documented identically

`served_drift` (`:1919`) calls `roster_drift` its **"twin"** with the **"Same refusal"**. But
`served_digests` has four write sites and **none re-stamps**: decode (rehydrate),
`promote_served_bank:1858` (set once at promotion), `top_up_served_digests:1899` (**"It only ever
ADDS"** — explicitly, at `:1885`), and the fail-closed drop. So **`served_drift` IS cumulative since
promotion.**

**Two functions, documented as twins with the same semantics, measure over different intervals.**

### The live 39-of-45, explained

39 of 45 checkable slots changed membership **in ONE hour** — 87%/hour churn, not 39 slots stale
since banking. Across 146 captured beats the building-bank rate is **median 70%, p75 85%, max 99%**.

**Corroborating identity:** units banked by `advance` carry no digest (`advance` is handed a key,
never a chunk — `:1833-1837`), so the next top-of-beat measurement cannot see them. Prediction:
`units_drift_uncheckable == units_completed_this_beat`. **Holds on 158 of 168 captured beats (94%),
and on today's live ledger (5 == 5).** Only a per-beat baseline produces that identity.

### The consumers believe the docstring

* `calibration_published_twin.py:74` — *"with `units_drifted` of `units_banked` has had **that share
  of its slots move**"* — a cumulative reading.
* `calibration_staged_disclosure.py:81-87` — reasons that a frozen bank under-reports so *"the real
  drift is `>=` the number published"*. Directionally still true, but the stated mechanism is wrong.

---

## 3. `P196-2` — `availability: fresh` is structurally unreachable, and it is user-visible

`build_disclosure` has two branches (`calibration_staged_disclosure.py:263-269`):

```python
:267    frozen_over_drift = not drift_known_zero                              # SERVING
:269    frozen_over_drift = (advanced is not True) and not drift_known_zero   # pre-CAL-P078
```

The module docstring's stated reason for having **no drift threshold** is satisfiability:

> **It is satisfiable by the ruled fix.** Once the bounded incremental re-stage lands, a beat with
> drift re-stages some of it, `units_this_beat > 0`, and `fresh` renders again.

That escape **is** the `advanced` term — and CAL-P078's serving branch deliberately removed it
(`:263-267`, "the builder's progress says NOTHING about whether the census being served has moved" —
correct on its own terms). **The justification for the no-threshold design does not survive into the
branch that now runs.** `fresh` now requires literally zero drift on the served bank.

### Measured over 168 consecutive production beats (2026-08-22 → 08-29)

| | beats |
|---|--:|
| `frozen_over_drift: true` → availability floored to **STALE** | **152** |
| `frozen_over_drift: false` → `fresh` permitted | **1** |
| disclosure unmeasured (`served_units 0`) | 15 |

**`fresh` was permitted on 1 of 153 measured beats — 0.7% of a week.** `served_drifted` sits at
**128/128 on 102 beats**.

### Why even the promotion beats fail — the one-beat offset

`drift_known_zero` needs **both** `drifted == 0` **and** `unknown == 0`. Twelve beats had genuinely
clean drift (`served_units 128, served_drifted 0`) — every promotion. **Eleven of the twelve were
blocked by `served_drift_uncheckable` alone (4–9 units)**: the units `advance` banked mid-promotion,
which carry no digest. `top_up_served_digests` fixes exactly that — **on the next beat**, by which
time an hour of churn has made `served_drifted` non-zero.

Confirmed on the one cycle where they aligned (beat indices 43→45):

| beat | `served_drifted` | `served_drift_uncheckable` | `frozen` |
|---|--:|--:|---|
| 43 `11:38:58` **promotion** | 0 | **9** | True |
| 44 `12:40:58` | 0 | 0 | **False** ← the only one in 168 |
| 45 `13:43:51` | **125** | 0 | True |

**The two conditions are offset by exactly one beat, by construction.** They aligned once in a week.

### It reaches the user

`frontend/app/calibration/page.tsx:717` renders a banner from `staleness`, and
`lib/calibrationStaleness.ts:192` maps `frozen_over_drift === true` → `kind: "frozen-inputs"` →

> **"The curve is current. The data behind it is older."** *128 of 128 units have drifted since …*

So `/calibration` carries a staleness banner on ~99% of beats in steady state. It is not *false* —
the census is older — but a banner that shows on 152 of 153 beats carries no information, and
"128 of 128" is saturation, not a measure of how wrong the curve is: **one market arriving in a slot
marks that slot drifted**, and 128 slots partition the whole futures population against hourly
ingestion.

⚠️ **And the sentence changes meaning across the branch, invisibly.** `staged.units_drifted` feeds
the banner from `served_drifted` when serving and from the per-beat `units_drifted` when not. The
copy says *"drifted **since** `staged_at`"* — correct for the cumulative branch, **wrong for the
per-beat one**, with nothing in the payload telling a reader which they are looking at.

---

## 4. `P196-3` — the CAL-P069 coverage pair is sampled across a mutation

CAL-P069 added `*_drift_uncheckable` so a zero could never read as measured. The two halves are
sampled on **opposite sides of the call that fills the gap**:

| half | where | when |
|---|---|---|
| `served_drift_units` | `retain_planned_units:1995` | **before** `top_up_served_digests` |
| `staged:served_drift_uncheckable` | `calibration_main_build:1517`, from the persisted cursor | **after** it |

The convergence read is **not** lagged — `_record_staged_convergence` runs from `save_phase_ledger`
at end of beat and sees its own beat's write (proof: beat 43 recorded `served_at 11:38:20` against
its own `generated_at 11:38:58`). So the two gauges describe **different populations of the same
bank in the same beat**: drift measured over the units that had digests, coverage computed over the
topped-up set.

Consequence at beat 44: the disclosure published `units_drift_unknown: 0` over 128 units when only
119 had been compared — and that is the single beat in 168 that rendered `fresh`. **The one time the
freshness gate opened all week, it opened on a coverage figure that had already been repaired
behind the drift figure it was paired with.**

*(Mechanism confirmed from source; the beat-44 attribution is the consistent reading of the captured
data, not an independent measurement.)*

---

## 5. What this is NOT

* 🔴 **Not a fix.** All three are parked. Ruling 134 makes them a fold's call; D-G freezes the deploy;
  ruling 009 freezes the module. **Nothing was edited in `app/` or `frontend/`.**
* 🔴 **Not evidence about the group-key hazard.** `category` is a **data value** absent from both
  digests. This is about the *interval* each digest is compared over, not its *columns*. **Seven
  consecutive sessions have now filed a ledger/digest park that leaves the group-key hazard
  untouched — it is still only recorded, never guarded.**
* ⚠️ **Not trap 18.** Trap 18 says never *grade a ship* on `served_drifted`. This is about what the
  gauge means and what it does to `availability`. Different axis — and trap 18 stands unchanged.
* ⚠️ **Not a reason to widen the fence, lift D-G, or change the ETA.** None of it touches the
  cancellation model or the duty cycle.
* ⚠️ **Not an argument that the banner should be removed.** The census genuinely is older. What is
  defective is a gate whose two conditions cannot co-occur, and a sentence whose "since" is branch-
  dependent.

---

## 6. Question bank, after P196

1. ***"what does this guard compare — and what is NOT in it?"*** — **SEVEN FOR SEVEN.** Aimed at a
   runtime guard again (P194's extension), and it worked again. Remaining unaimed: the `floors`
   ring, the fence model's `phase_bound`. 🔴 **Still the strongest question here.**
7. ***"the docstring and the guard disagree — which one does the CALLER believe?"*** — **TWO FOR
   TWO** (P194, P196). This session it paid on a *pure utility function*, not an accessor. **Live**
   — ~8 ledger accessors still unread against their consumers.
* 🆕 ***"this pair of gauges is meant to be read together — are they sampled at the same instant?"***
  Proposed by `P196-3`. Generalises: a coverage pair straddling a mutation is a new shape, and there
  are other pairs (`units_drifted`/`units_drift_checkable`, `banked`/`planned`).
* 🔴 **Exhausted/spent, unchanged:** q3 (P192), q4 (P193), "captured or only written" (P188),
  "is this comment still true" (P193, NEGATIVE).

**Fifteen consecutive sessions have found something by re-reading. That is a streak, not an
entitlement** — and an idle build lane remains a legitimate outcome (ruling 134).

---

## 7. Files

| file | what |
|---|---|
| `drift_semantics.py` / `.out.txt` | 12 source-containment checks, exit 0, runs from anywhere |
| `ring_reachability.py` / `.out.txt` | 168-beat tabulation over CAL-P118's reused ring, exit 0 |
| `REPORT.md` | this |
