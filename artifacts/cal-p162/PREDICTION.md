# CAL-P162 — the prediction, recorded BEFORE the code (directive 929)

**Recorded 2026-08-31, before the first line of the RULE E build.** Directive 929: *"State the
predicted `cells_at_bar` and headline after this batch deploys, before you write code."*

## Board at the moment of prediction

| | |
|---|---|
| published headline | `mce_closing_line` **1.86 pp**, `generated_at 2026-08-31T04:37:36Z`, population `q268` |
| board | **31 / 49 cells at bar** |
| unit bank | **75 / 128**, `input_fingerprint 75faaed6`, +5 units/beat |

## What is actually shipping in this batch, and what is not

Directive 929 named four cells. Measured against the repo rather than the 08-28 board:

| rank | cell | in this deploy? | why |
|--:|---|---|---|
| 1 | `polymarket/baseball` | ❌ **NO** | K′ = R1+R2+R3+M1. R1/R2 exist only on `program/calibration-99`, **not on master** — a 9,866-line / 28-file port. Not a same-session slice; handed forward |
| 2 | `kalshi/economics` | ✅ **YES** | RULE E + the `(kalshi, economics)` allowlist tuple |
| 3 | `polymarket/esports` | ✅ **YES** | RULE E — the esports category is the allowlist seed, so the structural arm reaches it in the same change |
| 6 | `kalshi/crypto` | ✅ **ALREADY DEPLOYED** | `fd033079` (CAL-P150, D12, 2026-08-30). The 08-28 board directive 929 quotes reads "unbuilt"; the code disagrees |

**RULE E2 is deliberately NOT built** — scorecard §6i **13-CAL** puts a HOLD on it (*"E2 must not
land before 12-CAL is decided"*), and E2 rides the same allowlist onto ranks 2 and 6. Cost: rank 2
lands at RULE E's **3.00** rather than E+E2+E3's **2.61**.

**RULE E3 is deliberately NOT built** — it drops `mutually_exclusive = true` from
`malformed_binaries`, which is a **global** widening of an exclusion measured only on esports (116
outcomes). Its curve-wide blast radius is unmeasured. Parked, not dropped.

## THE PREDICTION

| quantity | today | predicted after this deploy |
|---|--:|--:|
| **`cells_at_bar`** | **31 / 49** | **32 / 48** |
| **`mce_closing_line`** | **1.86 pp** | **1.78 pp** (band **1.70 – 1.86**) |

### How that number is arrived at, so a miss is diagnosable

* **rank 2 `kalshi/economics` crosses off.** 5.29 → **3.00** (§6b policy C, exact rail). 3.00
  against a 3.0 bar is *at* the bar, not under it — this is the single most fragile arm of the
  prediction. If the published population moves it to 3.01 the cell does not cross and the answer
  is **31 / 48**.
* **rank 3 `polymarket/esports` does NOT cross off.** 7.59 → **3.29** (exact rail, RULE E alone,
  CAL-P114 §5c). Still over its 3.0 bar. What it delivers is excess-outcomes **64,503 → ~3,371**,
  not a crossed-off cell. Said here so the report cannot later claim it.
* **rank 6 `kalshi/crypto` leaves the denominator.** RULE C takes it to 3 rows, under the 1,000-row
  floor, so it becomes an absence rather than a pass — **49 → 48**, already deployed, first
  measurable on the next published curve.
* **The headline falls, modestly.** The removed rows are high-error, so pooled MCE should drop; but
  `kalshi/economics` sits at gap −0.47 and `polymarket/esports` at +6.02, so removing them is
  **partly de-cancelling** (§2). That is why the band's top edge is *no change at all* rather than
  a fall. **If the headline RISES above 1.86, the prediction is refuted** and the cause to look for
  first is de-cancellation, not a broken filter.

### The falsifier, stated plainly

If the curve republishes and `kalshi/economics` is **not** at or under 3.0 pp, RULE E as built does
not do on the published population what the exact rail measured, and the rule must be re-argued —
not re-tuned.

## What this costs

The deploy resets `input_fingerprint`, which **zeroes the 75/128 unit bank** and restarts the
rebuild. That is the accepted price: directive 929 revoked the D34 hold precisely because the hold
was protecting the measurement instead of the thing being measured.
