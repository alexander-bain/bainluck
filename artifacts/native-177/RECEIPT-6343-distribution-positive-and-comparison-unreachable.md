# native/177 — #6343's last two card shapes: one photographed, one proved unphotographable

Date: 2026-09-15, ~10:15 PT / 17:15Z. Lane: native. Pillars: TRUTH · FORMATTING. Check 5.
Tree: `native/174-price-age-reveal-walk`, `ios/**` byte-identical to `origin/master`
(`git diff --stat origin/master -- ios` empty). Binary photographed: DerivedData build of
2026-09-15 07:06:25, resolved by `tools/native-shoot.sh --resolve-only`.

## What was open

YOUR-TURN check 5 carried, from native/173's own statement rather than from anyone's
complaint:

> Two card shapes have simulator screenshots; the other two have code/test evidence but no
> stale-card screenshot yet.

native/173 stated it plainly: "No production draw this session put a stale card on the
`outcome_distribution` or `cross_source_comparison` views, so those two are carried by the
source scan and the unit band and **not** by a photograph."

Those two are `DistributionCardView` and `ComparisonCardView`. This receipt closes both —
one with a photograph, one with a proof that no photograph can exist.

## 1. `outcome_distribution` — PHOTOGRAPHED

`artifacts/native-177/POSITIVE-distribution-alito-3d-ago.png`
(crop of `pol-10200.png`, full frame kept).

The card is **"Will Samuel Alito announce his retirement?"**, a `DistributionCardView`
(numbered ladder, `Distribution` chip in the footer). The price-age mark draws in the footer
row between the liquidity bars and the source chip:

> `Distribution` … `▮▯▯ ● 3d ago` `Polymarket`

**Tied to the served payload, not inferred from the pixels.** `GET /api/feed?limit=60`, same
minute as the shot, market `131023`:

| field | value | consequence |
|---|---|---|
| `discover_card.suggested_format` | `outcome_distribution` | first arm of the Distribution route |
| datable `distribution_outcomes` | 4 | `>= 4`, so the route is taken — not the hero fallback |
| `top_outcomes` | 3 | (see §2) |
| `price_observed_at` | `2026-09-11T23:50:18Z` | 89.4 h = 3.7 days |
| `source` | `polymarket` | the `Polymarket` chip in the shot |

89.4 h renders `3d ago`, which is what the photograph shows. Card body corroborates
independently: "Resolves Dec 30" and exactly four outcomes (June 30 2027 / December 31 /
February 28 / September 30).

**Two negative controls in the same frame**, which is why the full frame is kept: the hero
card above it ("This Sep 2026 is the hottest September ever?", fresh) draws no mark, and the
Distribution card below it ("Highest grossing movie in 2026?", fresh) draws no mark either.
Same component, same viewport, mark present only on the stale row.

**Read as a first-time reader (D48).** The mark is quiet — grey, lower-case, behind a small
dot, sitting with the sourcing furniture rather than with the numbers. It reads as sourcing,
not as an alarm; it takes no line away from the source chip; it does not crowd the ladder.
Consistent with the hero and heat-map positives of native/173.

## 2. `cross_source_comparison` — NO PHOTOGRAPH IS OBTAINABLE, AND THAT IS THE FINDING

`ComparisonCardView` has exactly one call site, `DiscoverView.swift:957-959`:

```swift
} else if item.type == "futures", let f = item.futures,
          (f.discoverCard?.suggestedFormat == "cross_source_comparison"
           || (f.topOutcomes?.count ?? 0) >= 4) {
```

**Both arms are unsatisfiable against the shipping backend.**

- **Arm A — the format string is never produced.** `cross_source_comparison` appears
  nowhere in `backend/app`, `backend/tests`, `frontend/components`, `frontend/lib` or
  `frontend/app` (`/usr/bin/grep -rn`, exit 1 on both greps — a result, not a harness
  story). It exists only in `ios/**`. Measured: 0 of 138 unique futures cards carried it.
- **Arm B — `top_outcomes` is structurally capped at 3.** Both feed futures serializers
  build it from `card_outcomes[:CARD_PRICE_AGE_LEG_COUNT]`
  (`routes/feed.py:9653` and `:11049`), and
  `CARD_PRICE_AGE_LEG_COUNT = 3` (`utils/futures_market_snapshot.py:574`). So `>= 4` cannot
  be true. Measured, agreeing with the code: across 138 unique futures cards over four feed
  pages the `top_outcomes` length distribution was `{3: 103, 1: 25, 2: 10}` — **max 3**.

Routing all 138 cards through the real cascade returns
`{Distribution: 64, hero: 41, HeatMap: 33, Comparison: 0}`.

**So `ComparisonCardView` is dead code in the shipping app**, and native/173 not
photographing it was structural, not bad luck. This is stated rather than left as
perpetual LOOK debt: nobody should spend another session hunting a specimen that the
serializer forbids.

**It is not a reader-visible defect and no issue is filed for it** (launch-week 49(c)).
Every card is rendered by something; a card that would have gone to Comparison falls to the
hero branch, which draws correctly. The cost is dead code plus one guard test that reads
stronger than it is:
`PriceAgeMarkTests.testEveryFuturesCardViewDrawsTheMark` asserts the mark is called in all
four view files. That guard is correct and worth keeping — it protects the route if it is
ever re-opened — but it must not be read as "four shapes a reader can see". Three can be
seen. Three have now been photographed.

## Coverage after this session

| shape | view | production route | stale photograph |
|---|---|---|---|
| `binary_probability` + fallback | `DiscoverFuturesCard` | live (41/138) | ✅ native/173 (`5d ago`), re-confirmed here (`3d ago` ×2, `pol-4500.png`) |
| `threshold_heatmap` | `HeatMapCardView` | live (33/138) | ✅ native/173 (`6h ago`) |
| `outcome_distribution` | `DistributionCardView` | live (64/138) | ✅ **this session** (`3d ago`) |
| `cross_source_comparison` | `ComparisonCardView` | **unreachable (0/138)** | ⛔ impossible — see §2 |

Every shape a reader can reach now carries a photographed stale mark.

## Two instrument findings, recorded because they cost this session time

1. **`tools/native-shoot.sh --cooled` no longer seeds anything.** The script writes the
   interaction-profile plist into the app's data container, but `simctl install` mints a
   **new** data container on each run (observed `57579BF8…` → `9F4E7EDE…`), so the seed is
   discarded before launch. Confirmed by reading back:
   `xcrun simctl spawn <sim> defaults read <bundle> discover_interaction_profile_native_v2`
   → "does not exist". Symptom is silent: the shot looks fine and shows an uncooled feed, so
   a `--cooled` LOOK reports the ordinary page while claiming to report the cooled one.
   Working route used here — seed *after* install and launch *without* reinstalling:
   ```
   xcrun simctl spawn $SIM defaults import $BUNDLE profile.plist
   xcrun simctl terminate $SIM $BUNDLE
   xcrun simctl launch $SIM $BUNDLE -suppress_notification_prompt YES … -launch_scroll N
   ```
   Not fixed here — it is tooling, it is not on the check-5 path, and one owner per fix.
2. **`-launch_scroll 99999` does not reach the bottom of Discover.** The feed is a lazy
   stack, so an over-ask clamps to whatever has been materialised and lands mid-page. The
   tool's "over-asking is safe: the app clamps" is true about crashing and false about
   arriving. Reaching a deep card needs a ladder, not one big number; `10200` points reached
   served-index ~49 here.

## Artifacts

Committed (an artifacts-only diff forces a Heroku release, so only the load-bearing frames
are kept; the rest of the hunt was read and then deleted rather than banked):

- `POSITIVE-distribution-alito-3d-ago.png` — the ship, cropped
- `pol-10200.png` — full frame: the positive plus its two in-frame fresh controls
- `pol-4500.png` — two hero `3d ago` marks (SAVE Act, Recession in 2027), corroborating that
  the same component draws the same mark on the shape native/173 already photographed

Read and discarded: 13 further frames from the scroll ladder and the two `--cooled` attempts
— fresh Distribution cards drawing no mark (further negative controls), and the
notification-alert frame that triggered the documented erase-and-reshoot. Their content is
described above; none of them carried a stale Distribution or Comparison card.
