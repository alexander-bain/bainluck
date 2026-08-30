# CAL-P145 — the refusal register was scoped to four sessions, and the board it could not see is 13 of 20 seats

**TL;DR.** D13 and D22 are still unanswered, so nothing landed and the freeze holds
(`git diff backend/` empty, `precompute_calibration.py` untouched, no exception requested).
The budget went where the directive pointed it — the refusal register — and extending it
turned up something decision-shaped rather than cosmetic:

1. 🔴 **The register carried 4 refusals; disk has 8 refusal documents covering 13 cells.**
   The four it could not see are not marginal: `polymarket/soccer` (**live rank 4**),
   the six `odds_api_bookmaker` cells (**ranks 5, 8, 13, 14, 18, 20**), `polymarket/cricket`
   (**rank 10**), `kalshi/golf` (**rank 7**).
2. 🔴 **13 of the 20 live board seats — 206,963 of 472,104 excess-outcomes (43.8%) — sit
   under a documented refusal.** That is `alex-inbox/calibration-908`'s "step 1 has selected
   the empty set for nine sessions" shown as a number instead of asserted.
3. 🔴 **Two of those refusals shipped a board correction that never reached Alex.** `17-CAL`
   (CAL-P127: `kalshi/golf` is not established, σ 1.42 vs a 2.0 gate — take it off the board)
   is nowhere in YOUR-TURN. CAL-P120's six-cell correction is measured and unactioned; it sits
   behind D11, whose default asks for a measurement whose **queue half is already done**.
   Filed as `alex-inbox/calibration-915`.
4. **The register can no longer go stale quietly.** It now reconciles against every
   `artifacts/*/RULE-DESIGN-*.md` on disk and exits 4 if one is unclassified — **proven by
   control** (planted an unregistered doc → exit 4; removed it → exit 0), not asserted.

The window is unchanged: **16 beats, 13 clean**, still arithmetically lost, not re-baselined.

---

## 1. What the extension actually is

`artifacts/cal-p145/refusal-register.py` (exit 0 live and on the banked render, ruff clean).
Three changes over CAL-P144's:

* **Keyed on the refusal DOCUMENT, not the cell.** CAL-P120 refuses six cells in one document
  and two documents touch `kalshi/entertainment`; the document is the only key that is
  one-to-one with "a search was run".
* **A `disposition` taxonomy that is load-bearing.** "no rule exists" (a search came back
  empty) and "not established" (the excess does not survive the right unit of observation) are
  different findings with different consequences. 8 cells are the first; 7 are the second.
  Collapsing them into "refused" is what let two board corrections go unactioned.
* **`refused_at` — rank and excess AS THE DOCUMENT STATES IT**, joined against the live board
  as drift. Where a document does not state a figure it prints `-`; `polymarket/tech`'s excess
  at refusal is the one such gap and it is **left absent rather than reconstructed** from a
  later render.

Every number in the table is quoted from the document it cites. Nothing was re-measured and no
refusal was re-litigated.

## 2. 🔴 The reconciliation, and why it is the point

CAL-P144's lesson was *an instrument that has never run its default path is a document*. The
row source has the same failure mode one level up: a register hand-listing four refusals
**reports its own scope as the world**, and it did — for two sessions, while rank 4 and rank 5
were both refused cells it had never heard of.

So the scan is over the **filesystem**, not over the register's own tables. Every rule-design
document must be classified as a refusal (with a citation) or with a named non-refusal
disposition; 9 are registered as non-refusals (banked / ruled / superseded / built-not-applied,
each quoting its own header). An unclassified document is exit 4.

**Control run, because a guard nobody has seen fire is a guard nobody has tested:** planting
`RULE-DESIGN-negative-control.md` produced `EXIT CODE: 4` naming the file; deleting it returned
`EXIT CODE: 0`. Both banked in this session's transcript.

## 3. What this says about the conveyor

| | seats | excess-outcomes |
|---|--:|--:|
| live queued cells | 20 | 472,104 |
| **under a documented refusal** | **13** | **206,963 (43.8%)** |
| of which "not established" (arguably should not be queued at all) | 7 | 102,412 |

The conveyor's step 1 selects from this board. Seven of its seats are cells a prior session
measured as *not statistically established* — the queue is ranking them above cells nobody has
searched. That is a queue-hygiene fact, not a new measurement, and it needs no cycle to act on.

## 4. The window — carried, not advanced

Same instrument, same log, **watcher verified single before anything else ran** (`pgrep -f
"rebaseline.py --baseline-at"` → pids 3016/3019, unchanged, zero restarts). Re-ran
`cal-p144/window-beat-margins.py`: **14 gauged beats, 14 agreements, 0 disagreements** — the
margin model is still exact and still load-bearing. No beat 17 had landed by 15:36 UTC; no
`failed/not_evaluated` beat went unattributed. **Not re-baselined** (D22 has not landed).

Tightest CLEAN margins unchanged: beat 11 by 4.3 s, beat 8 by 4.6 s, beat 16 by 7.3 s.

## 5. Deliberately not done

* **Landed nothing.** D13, D21, D22 remain Alex's and ungranted; CAL-P143's pre-builds are
  still applied nowhere. YOUR-TURN §4 re-read this session: both still unanswered.
* **Did not extend the missing-loser census** — 45 cells stay PARKED as CAL-P122-1 (ruling 134).
* **Did not build the class-B cure.** The reserve term in `_unit_fits_in_window` touches the
  frozen file; CAL-P144 costed it, nobody asked for it.
* **Did not re-measure any refused cell.** The register carries citations, not opinions.

## 6. A process bug worth naming (cost: nothing, this time)

An early `cd ~/bainluck` persisted across Bash calls and two document reads landed in the main
checkout instead of this worktree. Caught when a relative path 404'd. **The two files were
diffed and are byte-identical**, so the citations in `calibration-915` stand — but the check
was luck, not design. Gotcha #51's rule ("`-C` pins the DIRECTORY") has a read-side sibling:
*a relative path in a shared-worktree session is only as good as the last `cd` you forgot.*
Absolute paths from here.

## Evidence

| file | what |
|---|---|
| `refusal-register.py` / `.txt` | §1–3 — 8 documents, 13 cells, live board join, exit 0 |
| `scorecard-live.txt` | the live board this joins against (20 queued cells, 2026-08-30 15:2x UTC) |
| `~/bainluck/.claude/handoff/alex-inbox/calibration-915-*.md` | §3 — 17-CAL and the D11 split |
| `../cal-p144/window-beat-margins.py` | §4 — re-run, 14/14, exit 0 |
