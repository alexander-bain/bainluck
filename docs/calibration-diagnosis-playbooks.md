# Calibration Diagnosis Playbooks

Written 2026-07-06 (Fable). For every future thread that sees a janky /calibration chart. This encodes the discipline that was learned expensively (#938a, #941, #942 misdiagnoses) and is now pause-lift critical path (D5/D8 in `docs/decisions-2026-07-06.md`). **The cardinal rule: diagnose with rows before fixing with code, and never re-grade without authoritative proof (gotcha #21).**

## Step 0 — Is it real?

Before anything: bucket sample sizes and confidence intervals. A bucket with n < ~30 gets a note, not a work item — wide error bars ARE the answer (see the totals 75%→0% point). A "systematic" claim requires the bias to hold across ≥3 adjacent buckets with n ≥ 200 each, in the same direction. Also rule out the measurement artifact class first: mid-deploy cache invalidation (`computed_at: None` — wait one precompute beat), and recent exclusions changing the denominator between reads.

## Step 1 — Classify the anomaly shape

Each shape has a distinct suspect list. Match the chart to a row:

| Shape | Looks like | Suspects, in order |
|---|---|---|
| **Whole-curve offset** | Entire line above/below diagonal (datagolf today) | (1) Denominator/selection artifact — a filter removed a biased subset (e.g. void-filter excludes did-not-plays, who are mostly losers → survivors over-perform prediction); (2) source model bias (real, not ours); (3) capture-time skew (prices captured systematically early/late) |
| **High-bucket collapse ("hook")** | Calibrated below ~50%, crashes at the top (golf 95%→36% today) | (1) Stale/wrong capture on confident favorites (illiquid one-sided books, #938a/#941 class); (2) wrong-side resolution on a specific market family (#939/#942 class); (3) linkage collapse — markets pinned to the wrong event/date (gotcha #14, golf's chronic risk); (4) settlement aged out before capture (gotcha #35) |
| **Zero-winrate slab** | A price band with ~0% actual (the old pass2_loser 0.5–0.9 band) | Heuristic resolution poisoning — outcomes marked false without authoritative settlement. Statistically impossible bands are the tell. Fix = curve-exclude then authoritative re-resolve (the #754/#989 pattern), never bulk re-grade in place |
| **Noisy tails, huge CIs** | Isolated wild points at extremes | Small-n. Count it, note it, move on |

## Step 2 — The row-trace protocol (mandatory before any fix)

Pull 20 rows from the offending bucket (read-only, `POST /api/admin/db-query`). For each: market name + source, event linkage (event_id, commence vs resolution time — gotcha #14 check), when `calibration_probability` was captured and the book state then (one-sided?), `resolution_source`, and our `is_winner` vs an independent authoritative check (final score / CLOB / Kalshi settlement). Classify every row: `correct` / `wrong-resolution` / `wrong-linkage` / `stale-capture` / `illiquid-capture` / `aged-out`. The bucket's verdict is the majority class — and mixed verdicts mean multiple fixes, not one clever one.

## Step 3 — Route by verdict

- `wrong-resolution` + an authoritative source exists → targeted re-grade queue (Lane 1), scoped to the proven family only, idempotent, with a distinct resolution_source. This is the ONLY verdict that permits touching is_winner.
- `wrong-linkage` → relink (event_id/commence_time), then let resolution recompute. Never re-grade a mislinked market in place (#942's lesson — the premise was linkage, not resolution).
- `stale/illiquid-capture` → NOT code-fixable (#938a/#941's lesson). Route to the liquidity-tier methodology (D2): these belong in the thin tier, excluded from the headline curve. Do not invent price corrections.
- Selection/survivorship → fix the DENOMINATOR in the precompute (read-side, like #754), or display both filtered/unfiltered. Never mutate data to fit the chart.
- `aged-out` → document the count as the honest floor. The capture window (~2–3 months, gotcha #35) is a fact, not a bug.

## Worked entries for the three current cases (D8)

**datagolf (whole-curve offset, actual ≈ predicted + 8–15pp):** Test the survivorship hypothesis first — compare the curve WITH did-not-play/withdrawn outcomes restored to the denominator vs the current void-filtered curve. If the offset shrinks toward the diagonal, the void filter is biasing the sample (withdrawals are disproportionately losers) and the fix is methodological: either count DNPs as losses for calibration purposes (they were priced and didn't win) or show the filter's effect transparently. If the offset survives the test, it's a genuine DataGolf model bias — display honestly, consider a blend-weight note, do NOT "correct" their probabilities. Either way: no re-grades.

**golf category (hook: predicted 95% → actual 36%):** Row-trace the 85–95% buckets. Golf's priors say check linkage first (Kalshi golf timestamps are close-times, round-leader markets collapse onto wrong days — gotcha #14) and capture second (round-leader books go one-sided late, #938a). A 95%-predicted favorite losing 64% of the time at volume is almost certainly OUR artifact, not golfers choking — treat any "genuine losses" conclusion with maximum suspicion until the trace proves it.

**totals 75%→0%:** Count the bucket first. If n < ~30: annotate as noise, done. If material: check for a residual inverted family the #945 re-grade missed (a specific series or season slice), then row-trace per protocol.

## Standing links

Gotcha catalog: `docs/gotchas-reference.md` (#14, #17, #21, #23, #35 are the calibration five). Decision register: `docs/decisions-2026-07-06.md`. Prior incidents: #937/#938a/#939/#941/#942/#944/#945 (the 2026-06 chain — read before proposing any re-grade). Verify-before-regrade is a hard staging gate, not advice.
