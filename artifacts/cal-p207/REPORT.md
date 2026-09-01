# CAL-P207 — CERT-697 IS GREEN; and the beat-TIMING report is gated on the CURSOR read

**Session:** 2026-09-01, ~14:3x–15:0x PT. Directive `977-burndown-conveyor.md` (self-staged by
CAL-P206). Branch `program/calibration-190-the-rebuild-survives-a-deploy`.
**Built: nothing. Merged: nothing. Deployed: nothing. `calibration-205` untouched at `293ed0e9`.**

---

## 0 — HEADLINE

1. 🟢 **`CERT-697` IS GREEN — TOKEN GRANTED.** 2026-09-01 21:26Z, subject `293ed0e9` against base
   `b5c59f38`. The lane's only open ship is cleared and is now blocked **solely by the freeze**.
2. 🔴 **`P207-1` — the beat-TIMING report is gated on the CURSOR read, and its docstring promises
   the opposite.** Proven at source, **LATENT** in production (0 hits / 168 beats). It is also the
   **NINTH** member of `P206-1`'s one-read family, and it escaped `P206`'s own stated detection
   rule.
3. ⚠️ **`P207-2` — a second independent live beat corroborates `P206-2`** (n=1 → n=2): published
   `beats_to_publish = 3` against a measured truth of **12**, i.e. **4.0× optimistic**.

---

## 1 — STANDING CHECKS (all four, in order)

| check | result |
|---|---|
| Local fingerprint predictor | `e2040f90154fae876f0fb65f5abf74c3` — **unchanged, forty-first session** |
| `origin/master` | `b5c59f38fd1847ccb503f7ea2ad7f1f4a055c5d8`, **empty diff — SEVENTH quiet session** |
| `/api/calibration` `generated_at` | `2026-08-31T04:37:36Z` → **before `2026-09-02`. FREEZE STILL ON.** |
| `availability` | `stale`; `temporary_excluded` / `temporary_by_cell` both **absent** |
| Inbox `ls` (start) | only `977-…md.running`. **No new Fable directive.** |
| `STANDING-NOTICES.md` | mtime 14:15, clause 2 verbatim as quoted in the conveyor — **unchanged** |
| `TOP-PRODUCT-DEFECTS.md` | 24 items; only 12 and 21 touch calibration, **neither is a calibration-lane build item** |

**Both bank-bearing rows (ITEM 1b), 21:36:12Z:**

| row | updated_at | generation | bank | ledger copy |
|---|---|---|---|---|
| `…:staged_futures` (cursor) | 21:21:26Z | `1788297300187` | **70** | — |
| `…:phase_ledger` | 21:33:53Z | `1788297300187` | — | **70** |

**Generations AGREE ⇒ converged.** The beat P206 caught in flight (cursor at gen `…300187`, ledger
still at `…786268`, 70 vs 65) reported at 21:33:53Z. **Bank 70/128, 58 to go.** Owner
`b9f90add…:207`, lease `1788299546`. **P185's discriminator: 0 rows** (P185–P189, P199, P202–P207).

---

## 2 — `CERT-697`: GREEN, TOKEN GRANTED

`CODEX-CERT-LOG.md:840`, 2026-09-01 21:26Z:

> **GREEN — TOKEN GRANTED.** The wide fingerprint remains the base/live `e2040f90`; a
> production-shaped 65-unit legacy cursor resumes with all units, serializes under narrow
> `78143607`, then resumes normally. Exact-head cutover 26/26, adjacent calibration/cursor 416/416,
> derived-map 6/6, identity and diff hygiene pass; author-banked full backend is 25,632/0.
> **Token granted for `293ed0e9` against `b5c59f38`.** … **The hard deploy freeze remains.**

Three things follow, and one is a trap.

* 🟢 **GRADE-THIS #2 was independently satisfiable and P206 had already satisfied it** — the live
  production `input_fingerprint` equals the local predictor at `293ed0e9`. The certifier reached
  the same verdict by its own route.
* 🔴 **IT STILL MAY NOT MERGE.** PROCESS-V2 clause 3 (self-merge Tier-2 on cert GREEN) is
  **overridden** by `STANDING-NOTICES` clause 2 and conveyor ITEM −2. The cert row says so itself.
  **The gate is the literal date `2026-09-02` on `/api/calibration` `generated_at`.** Today it
  reads `2026-08-31`. **Not merged this session, by rule, not by omission.**
* ⚠️ **THE BUS DISAGREES WITH ITSELF — read the LOG, not the QUEUE.** `CERT-QUEUE.md:36894` still
  reads `status: staged` / `owner: unclaimed`; the cert log reads GREEN/TOKEN GRANTED. The cert
  bus's own status line calls CERT-697 "**malformed no-`queue_id`**". Per
  `reference_cert_log_is_the_merge_authority`, **`CODEX-CERT-LOG.md` wins.** A session that greps
  `CERT-QUEUE.md` alone will conclude this ship is still ungraded. It is not.

**FOLLOW-UPs raised by the certifier, none disproving the ship:**
`CAL-P205-UNIT-SEMANTICS-FINGERPRINT` · `CAL-P205-CUTOVER-RESTAMP-WITHOUT-PROGRESS` ·
`CERT-BUS-QUEUE-ID-REQUIRED`.

**PC-1 stays pre-registered and unchanged** — on the first beat after it deploys,
`staged:cursor_reason:legacy_fingerprint_accepted` exactly once ⇒ worked;
`…:input_fingerprint_changed` ⇒ falsified and the bank was wiped. **Negative control: the cursor's
`committed_units` must not drop to 0 across that deploy.** 🆕 **Baseline refreshed: 70/128 at
21:21:26Z**, and the live ledger carries `staged:cursor_reason:resumable` (the pre-cutover steady
state, a baseline and not a result).

---

## 3 — Q13 ON THE BOARD (the cheapest question, run as instructed)

ITEM 3's "✅ built/merged/deployed" claims, re-verified by ancestry rather than trusted:

| claim | check | result |
|---|---|---|
| rank 1 `polymarket/baseball` merged `2aac5843` | `git merge-base --is-ancestor` | 🟢 **YES** |
| rank 6 `kalshi/crypto` deployed `fd033079` | `git merge-base --is-ancestor` | 🟢 **YES** |
| `CERT-697` subject `293ed0e9` NOT on master | `git merge-base --is-ancestor` | 🟢 **NO — freeze honoured** |

Content diff `origin/master` ↔ `calibration-205`: 7 files, +767/−8, 3 production files. Unchanged.
**No board claim was found false. Q13 is now 1-for-1 positive (P204/P205) and 1-for-1 negative here
— a negative is the expected result and the reason the question is cheap.**

---

## 4 — 🔴 `P207-1`: THE BEAT-TIMING REPORT IS GATED ON THE CURSOR READ

**Question:** Q7 (*"the docstring and the guard disagree — which one does the CALLER believe?"*)
crossed with Q15 (*"how many keys does this ONE read feed?"*), pointed at the reporting path
`P206-1` did **not** cover.

### 4.1 What the docstring guarantees

`_record_staged_rate` (`calibration_main_build.py:1531`) makes three explicit promises:

> "How fast this beat went and how many beats are left, **on EVERY terminal**."
> "…the divisor is already in hand here — **on the path that always runs, whatever the terminal**."
> "Every branch below either records a number or records WHY it could not (ruling 075, second
> clause). **None of them records nothing.**"

The docstring's whole subject is CAL-P066: the projection *"is skipped on every beat that does not
publish, which since 2026-08-02 is every beat"*, and this function exists to move it onto a path
that cannot be skipped.

### 4.2 What the caller does — AST-verified, ARM 1

`_record_staged_rate` has **exactly one call site**: `:1417`, **inside**
`_record_staged_convergence`, **inside its `try`**, **downstream of the single durable read at
`:1394`**, and behind **three early `return`s** at `:1401`, `:1405`, `:1409`:

```
:1399  not read.ok / envelope is None   -> convergence_reason:{status}   -> RETURN
:1403  payload is not a dict            -> convergence_reason:payload_shape -> RETURN
:1407  committed_units is not a list    -> convergence_reason:no_committed_units -> RETURN
:1418  any exception                    -> convergence_reason:read_raised
```

**Five of the six gauges `_record_staged_rate` emits need nothing from that read.**
`units_this_beat`, `units_completed_this_beat`, `unit_cost_reason:no_unit_completed`,
`unit_ms_mean_completed`, `rate_reason:no_unit_ran` and `unit_ms_mean` all come from
`runner.ledger` **in-memory** state that is fully available whatever the cursor row says. Only
`beats_to_publish` needs `banked`.

🔴 **So a CURSOR-read failure silently erases the BEAT-TIMING report** — and it does so on exactly
the beat an operator most wants to read, because the same failure means the bank is unreadable too.
**CAL-P066 moved the projection off one skip path and onto another.** The docstring's central
promise — *"none of them records nothing"* — is void at the call site: on all four exits,
`_record_staged_rate` records nothing at all, and the only trace is a `convergence_reason` that
names the *cursor* problem, not the missing timing report.

### 4.3 🔴 It is the NINTH member of `P206-1`'s family — and it beat `P206`'s own detector

`P206-1` counted **eight** gauges off the single read at `:1394` and generalised the tell as:

> "follow the payload into HELPER FUNCTIONS — `_record_drift_coverage` and `_record_served_bank`
> **take `payload` as a parameter**, so the family is wider than the call site."

`_record_staged_rate` is the **third** helper on that read and it does **not** take `payload`. It
takes **`banked=len(committed)`** — a derived **scalar** (AST-confirmed at the call site). A reader
applying P206's stated rule literally finds 8 and stops.

> **The family is NINE, not eight, and the ninth is `staged:beats_to_publish`.**
> **The rule must widen from "takes the payload" to "takes ANY value DERIVED from the read,
> including a scalar."**

Both `P206` findings therefore land on the same key from opposite directions: `P206-2` says
`beats_to_publish` is biased optimistic by construction; `P207-1` says it is also a beat-END copy
and its whole sibling family is gated on a read it does not need.

### 4.4 Honest limits — ARMS 2–5

`artifacts/cal-p207/rate_family_gated_on_cursor_read.py`, over the 168-beat ring:

| arm | result |
|---|---|
| ARM 1 — source fact | 🟢 **CONFIRMED.** 1 call site, in-`try`, read at `:1394` precedes it, 3 dominating returns, kwarg `banked=len(committed)` |
| ARM 3 — fraction classified | **168/168 = 100.0%** |
| ARM 2 — hit shape | a beat carrying `staged:convergence_reason:*` AND missing `staged:units_this_beat` |
| — observed hits | **0** |
| — beats with a cursor-read failure | **0** |
| — beats missing `units_this_beat` | **0** |
| ARM 5 — dissociable? | 🔴 **NO.** With zero read failures the gated and ungated hypotheses are **indistinguishable on this population** |
| **verdict** | **NOT-OBSERVED (LATENT)** |

🔴 **This is a proven SOURCE coupling with ZERO demonstrated production hits. It is LATENT, and the
harness refuses to call it a defect-in-fact.** Same discipline as `P206`'s `UNTESTABLE`.

**Why it stays latent, measured:** `STAGED_FUTURES_SCHEMA = "calibration-staged-futures/v1"` — the
only value it has ever held, and **`CERT-697`'s branch does not touch it**. The remaining triggers
(row absent, payload not a dict, age > `STATE_MAX_AGE_S` = 14 days, an exception) are all rare.
**The realistic future trigger is a schema bump**, which would blank the timing report on the first
beat after the deploy that caused it.

🟢 **No wrong published number is possible by this route.** The publication gate is
`is_complete(cursor, chunks)` and reads the **cursor** (`P203-1`, re-affirmed). **The cost is
OPERATOR-only** — the same shape as every finding in this run.

🔴 **DO NOT FIX IT.** Hoisting `_record_staged_rate` above the read is a three-line change with a
real argument against it (`banked` would have to become optional, and `beats_to_publish` would need
a fourth convention for "bank unknown" — this denominator has already been guessed at twice, see
`P206-2`). **A fold's call under ruling 134.** Parked.

---

## 5 — ⚠️ `P207-2`: A SECOND LIVE BEAT CORROBORATES `P206-2`

`P206-2`'s explicit caveat was that its post-fix magnitude *"rests on ONE live beat plus a
monotonicity argument — it is NOT a population result."* The 21:33:53Z beat is an **independent
second observation**, read from the live ledger:

| quantity | value |
|---|---|
| `staged:units_this_beat` | 7 |
| `staged:units_completed_this_beat` | **5** |
| `staged:units_cancelled` | 2 |
| `staged:unit_ms_mean_completed` | 66,839 ms |
| `staged:unit_ms_mean` | 154,378 ms |
| `staged:beats_basis:completed` | 1 — **the CAL-P068 fix is engaged** |
| `staged:units_banked` | 70 ⇒ 58 remaining |
| **`staged:beats_to_publish` (published)** | **3** |
| **measured truth** (window ÷ units BANKED = 1,380,000 / 5 = 276,000 ms; 58 ÷ 5) | **12** |

> **Published 3 vs measured 12 — 4.0× optimistic.** P206's beat: published 4 vs measured 13
> (3.25×). **Two independent live beats, both 3–4× optimistic, both on the completed basis.**

⚠️ **n is now 2, not 1. It is still NOT a population result and must not be quoted as one.** The
168-beat pre-fix arm (median **1.30×**, 137/152 beats) remains the only population-scale number,
and it measures the *pre-fix* arm.

---

## 6 — WHAT WAS NOT DONE, AND WHY

* **No merge, no master push, no deploy.** The freeze binds; `CERT-697` GREEN does not lift it.
* **No fix for `P207-1` or `P207-2`.** Ruling 134 — both are a fold's call. Parked.
* **No layer 2 / layer 3.** `920` and the conveyor rule layer 1 only.
* **No new instrument as a queue** (PROCESS-V2 clause 6). The two harnesses answer a question and
  are parked as artifacts, not stood up as sentinels.
* **`TOP-PRODUCT-DEFECTS.md` not edited.** Build lanes do not add items; neither finding is
  user-visible.
* **`YOUR-TURN.md` not edited.** Lanes may not.

**Nothing was asked of Alex** (PROCESS-V2 clause 7).
