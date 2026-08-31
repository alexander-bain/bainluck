# CAL-P146 — the window's one datapoint about the calibration landed, was counted, and was never read

**TL;DR.** Nothing landed and the freeze holds — `git diff backend/` empty,
`precompute_calibration.py` untouched, no exception taken, D13/D22 both still unanswered in
YOUR-TURN §4 (re-read this session, file unmodified since 07:12 PT). The three carried
instruments were run and are green. The budget then went to the window, and it turned up
something the last three sessions walked past:

1. 🔴 **Beat 14 promoted a NEW census — the window's first and only MEASUREMENT — and no
   session read it.** CAL-P143's handoff render *counted* it (`MEASUREMENT ... : 1`,
   `promotions inside it: 1`); CAL-P143/144/145's READMEs do not mention it. CAL-P140's
   framing — *"not one beat in this window is a datapoint about the calibration"* — has been
   false since 12:24:39 UTC and was still being carried forward.
2. ✅ **What it says is good news: the headline HELD at 1.88 pp across a real recompute.**
   Bit-identical `headline_mce_closing_line`, `headline_ci`, `headline_pass`,
   `population_version` across all five in-window renders, while eleven other board fields
   moved — so this is not the stale-key failure mode (`a fresh generated_at hides dead
   writers`). The producer rebuilt 128 units and published unattended, under freeze.
3. 🔴 **The other half of the datapoint is unreadable, permanently.** The nearest banked render
   before the promotion is beat 8 (6 beats / 8 h earlier), the nearest after is beat 16. Ten
   fields moved across that bracket — including the NEEDLE, 30/49 → 29/49 — and none can be
   attributed, because the payload demonstrably drifts *within* a census. The directive's rule
   about MISS beats (*seen late it is unattributable FOREVER*) turns out to hold for the
   MEASUREMENT beat too, and nobody had written that down.
4. **That failure is now a non-zero exit, proven on both paths.**
   `promotion-datapoint.py` exits **4** on the live state and **0** on a planted adjacent
   bracket, where it correctly isolated the single planted change.

Window unchanged otherwise: **16 beats, 13 clean, 3 misses (all attributed)**, still
arithmetically lost (13 + 8 = 21 < 22), **not re-baselined**.

---

## 1. Carried instruments — all three run, all green

| check | result |
|---|---|
| watcher singleton (`pgrep -f "rebaseline.py --baseline-at"`) | pids **3016/3019**, unchanged, 10h56m, zero restarts — verified BEFORE anything else ran |
| freeze | `git status --porcelain` clean at entry; `git diff backend/` empty; only `artifacts/cal-p146/` added |
| D13 / D22 | **both still unanswered**; YOUR-TURN.md mtime 07:12 PT, no answer markers. Nothing applied. |
| `cal-p144/window-beat-margins.py` | **exit 0 — 14 gauged, 14 agreements, 0 disagreements.** Model still exact. Tightest CLEAN margins unchanged: beat 11 by 4.3 s, beat 8 by 4.6 s, beat 16 by 7.3 s |
| `cal-p145/refusal-register.py` | **exit 0** — no unregistered `RULE-DESIGN-*.md` on disk (re-run after this session's writes; this session authored no rule design) |
| unattributed misses | **none**. Beats 4 (B), 7 (C), 15 (B) all attributed. Beat 4 was `B_OR_D_UNATTRIBUTED` at CAL-P143's handoff and has since been resolved to class B, which the margin model independently agrees with |
| beat 17 | had not landed by **15:46 UTC** (beat 16 at 14:38; spacing has run 57–77 min) |

## 2. 🔴 The MEASUREMENT beat

`staged_at` is the discriminator (CAL-P140 §2). It sat at `2026-08-29T20:18:32Z` for beats 1–13
and moved to `2026-08-30T12:24:39Z` at beat 14, where it remains:

```
beats  1..13   staged_at 2026-08-29T20:18:32   datapoint REPUBLISH / MISS / MEASUREMENT_UNKNOWN
beat  14       staged_at 2026-08-30T12:24:39   datapoint MEASUREMENT   <- the promotion
beats 15,16    staged_at 2026-08-30T12:24:39   datapoint MISS, REPUBLISH
```

**A near-miss worth recording.** My first read of the same log was that the rebuild had been
*destroyed* six units from the finish — it stands at 122/128 on beat 13 and 0/128 on beat 14.
That is precisely the trap CAL-P140 §2 already documents and disarms (*"eight rebuilds dying one
to nine units short — which is what I wrote down before checking, and it would have been a
spectacular finding and false"*): promotion happens *inside* the beat that completes it, so the
counter returning to zero means harvested, not discarded. The banked README caught me. It is the
second time in three sessions that this lane's own prior write-up has been the thing that stopped
a false finding, which is an argument for the READMEs, not for me.

## 3. What the datapoint says, and what it cannot

Five renders are banked inside the window. Four are census A, one is census B:

| render | beat | census | headline | CI | at bar |
|---|--:|---|--:|---|--:|
| `cal-p139/scorecard.txt` | 3 | A | 1.88 | [0.86, 1.97] | 30 |
| `cal-p140/`, `cal-p141/scorecard.txt` | 6 | A | 1.88 | [0.86, 1.97] | 30 |
| `cal-p142/scorecard.txt` | 8 | A | 1.88 | [0.86, 1.97] | 30 |
| `cal-p145/scorecard-live.txt` | 16 | **B** | **1.88** | **[0.86, 1.97]** | **29** |

**READ:** the headline held. Identical in every render, so no gap can be hiding a move in it.

**NOT READ, and not readable:** everything else. The bracket around beat 14 is **6 beats before,
2 after**. A two-beat within-census control (beat 6 → beat 8, same census) shows the payload
already drifts on its own — `cells_total` 290 → 291, `total_outcomes` 925,466 → 926,007 — so an
eight-hour bracket cannot separate the promotion from ordinary drift. The instrument prints those
ten fields as `(unattributable)` rather than claiming them.

Two attribution traps handled explicitly:

* **`measured_sigma.*` is excluded from attribution entirely.** It is a CAL-P128 *ledger overlay*
  (`calibration_scorecard._attach_measured_sigma`), written out of band by sessions, not census
  output — so `refuted_cells` gaining `polymarket/economics` across the bracket is **not**
  evidence about the promotion. I had it in the attributed column until I read the writer. That
  is CAL-P139's lesson 24 arriving a third time: *read the writer before you trust the column.*
* **The board's printed `sigma` and `measured_sigma` are different quantities** and the source
  says so in as many words (`SIGMA_BASIS_ROW` vs `SIGMA_BASIS_MEASURED`). `kalshi/golf` prints
  2.6 on the board and is 1.42 measured; reading the printed column as the gate would invert
  17-CAL.

## 4. The instrument

`artifacts/cal-p146/promotion-datapoint.py` — ruff clean, banked output beside it. It finds every
`staged_at` transition, inventories every banked render on disk and maps it to its beat, brackets
each promotion, splits *survives the confound* from *unattributable*, and **exits 4 when a
promotion was counted but cannot be read.**

**Both paths fired, because a guard nobody has seen pass is as untested as one nobody has seen
fail** (CAL-P145's lesson, applied to the other direction — here the *failing* path is the live
one, so the *passing* path was the untested one):

```
live state                         -> EXIT CODE: 4   "beat 14 was COUNTED but cannot be READ"
planted adjacent bracket (13, 14)  -> EXIT CODE: 0   isolated exactly the one planted change
                                                     (counts.cells_at_bar 30 -> 29)
control removed, re-run            -> EXIT CODE: 4   (state restored; git clean)
```

## 5. Deliberately not done

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted. CAL-P143's two pre-builds are
  still applied nowhere; `land-12cal.sh` was not run.
* **Did not re-baseline** — D22 has not landed, and the directive forbids it.
* **Did not build the class-B cure.** Still touches the frozen file; still nobody has asked.
* **Did not extend the missing-loser census** — 45 cells stay PARKED as CAL-P122-1 (ruling 134).
* **Did not re-measure any refused cell**, and authored no `RULE-DESIGN-*.md` (so the register's
  reconciliation is unaffected — re-run, still exit 0).
* **Did not bank a fresh live render.** Tempting, since §3's whole complaint is a missing render
  — but a render banked now brackets nothing; the one that matters is on the *next* promotion,
  and the instrument will now demand it.

## Evidence

| file | what |
|---|---|
| `promotion-datapoint.py` / `.txt` | §2–4 — the instrument and its live exit-4 output |
| `../cal-p144/window-beat-margins.py` | §1 — re-run, 14/14, exit 0 |
| `../cal-p145/refusal-register.py` | §1 — re-run, exit 0 |
| `../cal-p140/README.md` §2 | §2 — the counter-reset trap that caught my first read |
| `../cal-p143/window-at-handoff.txt` | §2 — where the promotion was counted and left |
| `~/bainluck/.claude/handoff/alex-inbox/calibration-916-*.md` | the FYI, folds with 913/914 |
