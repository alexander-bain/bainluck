# Calibration Project

**Goal**: Every resolved prediction in our DB has an accurate opening probability and an authoritatively-determined outcome, so we can measure calibration at any granularity and trust the result.

**Principle**: No shortcuts. If we don't know the real outcome, we exclude it and document why. If we're guessing, we flag it and fix it. If we broke something, we document what happened and make sure it can't happen again.

**Monitor**: `GET /api/admin/calibration/decomposition` (automated, every 6h) + this document (manual, updated every session)

---

## 1. Current State (May 21, 2026)

| Metric | Value |
|--------|-------|
| Total resolved outcomes in DB | ~1,015,000 |
| In calibration | ~515,000 (51%) |
| Overall MCE | 9.8pp |
| Sources | 5 (Kalshi, Polymarket, Odds API moneyline, Odds API spreads, Odds API totals) |
| Per-bookmaker moneylines | NOT YET INCLUDED — needs precomputation (estimated +200K outcomes) |

---

## 2. Resolution Sources & Authority

| Market type | Authoritative source | Forward capture? | Historical backfill? | Confidence |
|---|---|---|---|---|
| **Moneyline (game winner)** | Event.home_score > away_score | ✅ Always | ✅ N/A (scores always captured) | Exact |
| **Spreads** | (home_score - away_score) + spread > 0 | ✅ Always | ✅ N/A | Exact |
| **Totals** | (home_score + away_score) > line | ✅ Always | ✅ N/A | Exact |
| **Kalshi game moneyline** | Kalshi API `result` field | ✅ Forward capture in polling | ✅ Re-verifies last 90 days | Exact (when API has data) |
| **Kalshi player props** | ESPN box_score_data | ✅ After box score backfill | ⏳ In progress (ESPN ID + box score backfill) | Exact (when box score exists) |
| **Kalshi period props (1H/2H/Q)** | scoring_plays table | ✅ After scoring plays captured | Partial (scoring_plays coverage varies) | Exact (when scoring plays exist) |
| **Kalshi game spreads/totals** | Parse line from name + Event scores | ✅ Always | ✅ N/A | Exact |
| **Polymarket game markets** | Polymarket API outcomePrices | ✅ Phase 3 in backfill | ✅ Gamma API lookups | Exact (when API has data) |
| **Polymarket settlement prices** | current_probability = settlement | ✅ Via polling | ✅ N/A | Exact (when price settled to 0/1) |
| **DataGolf tournament winner** | Leaderboard position = 1 | ✅ Leaderboard stored | ✅ Cross-reference with Kalshi | Exact |
| **DataGolf top-5/10/20** | Leaderboard position ≤ threshold | ✅ Leaderboard stored | ✅ Cross-reference | Exact |
| **DataGolf make-cut** | Numeric position (not CUT/MC/WD) | ✅ Leaderboard stored | ✅ But only top 50 players | Exact for top 50, unknown for 51+ |
| **Golf H2H** | Compare leaderboard positions | ✅ Cross-reference | ✅ | Exact (when both players in leaderboard) |
| **Pass 2 arbitrary pick** | Highest current_probability | N/A | N/A | **GUESS — not authoritative** |
| **Pass 1 clean resolution** | All outcomes at ≥0.95 or ≤0.05 | ✅ Always | ✅ | High (market settled to extremes) |

### What has NO authoritative resolution:
- First basket/goal scorer (need play-by-play scorer identity)
- Announcer mentions (broadcast-dependent)
- MLB total bases (ESPN doesn't report)
- Esports (no box score or score data)
- Economics/politics/weather non-event markets (Kalshi API only — purged after ~90 days)
- Golf round leaders, winning score, cut line, win margin

---

## 3. Active Backfills

| Name | Schedule | Batch | Est. completion | Dependencies |
|---|---|---|---|---|
| **backfill-winners** | Every 6h at :45 | All phases, limit 5000 | Ongoing | None |
| **backfill-box-scores** | Every 6h at :15 | 200 games | ~10 days for 979 remaining | ESPN ID must be set |
| **backfill-espn-ids** | Every 6h at :45 | 200 events | ~weeks for full historical | None |
| **backfill-polymarket-history** | Every 6h at :00 | 500 outcomes | Ongoing | None |
| **backfill-kalshi-history** | Every 6h at :30 | 500 outcomes | Ongoing | None |
| **backfill-historical-links** | 8x/day at :30 | 500 markets | Ongoing | None |
| **backfill-polymarket-open-sparse** | Every 6h at :15 | 100 outcomes | Ongoing | None |
| **backfill-kalshi-open-sparse** | Every 6h at :45 | 100 outcomes | Ongoing | None |

**Pipeline**: ESPN ID backfill → box score backfill → player prop resolution (in backfill-winners)

---

## 4. Known Exclusions

| What | Count | Why | Permanent? | Forward capture? |
|---|---|---|---|---|
| **Outcomes with null opening_probability** | ~484K | No real price captured; ask-price corruption cleaned | Partially fixable via snapshot restoration | ✅ Polling fix deployed (ask fallback capped at ≤0.50) |
| **DataGolf model predictions** | ~13K | opening_prob is model output, not market price | Permanent for DataGolf source | N/A — DataGolf is a model, not a market |
| **Esports (Kalshi)** | ~10K | No ESPN coverage, no box scores, no score data | Permanent unless we add an esports data source | Kalshi API resolves going forward (90-day window) |
| **Economics/politics/weather markets** | ~5K | Non-event markets resolved only by Kalshi/Polymarket API | Partially — API resolves recent; old ones purged | ✅ Forward capture via Kalshi polling |
| **First basket/goal scorer** | ~1K | Need play-by-play with scorer identity | Permanent with current data | No |
| **Announcer mentions** | ~200 | Broadcast-dependent, no data source | Permanent | No |
| **Golf round leaders** | ~500 | Need per-round leaderboard data | Fixable if we store round snapshots | Partially (DataGolf has round data) |

---

## 5. Granular Health Tracking

*To be populated by automated decomposition endpoint. Current known problem areas:*

### Tier 1 Leagues (expect near-100% authoritative resolution)

| Source × League × Type | MCE | N | Resolution quality | Issue | Action |
|---|---|---|---|---|---|
| Kalshi × NBA × player_prop | ~14pp | ~25K | Mixed (API + Pass 2 guess) | Old markets have Pass 2 guesses | Kalshi API re-verify (last 90d), ESPN box score backfill |
| Kalshi × MLB × player_prop | ~12pp | ~13K | Mixed | Same as NBA | Same |
| Kalshi × NHL × player_prop | ~14pp | ~4K | Mixed | Same + 308 ESPN "unavailable" NHL events | Investigate NHL ESPN parsing |
| Kalshi × PGA × tournament | ~14pp | ~500 | Leaderboard cross-ref deployed | Tournament name matching working for majors | Expand tournament coverage |
| Odds API × all × spreads | 2pp | ~10K | 100% authoritative (game scores) | ✅ FIXED | None |
| Odds API × all × moneyline | ~1pp | ~20K | 100% authoritative | ✅ Healthy | None |

### Per-Bookmaker (NOT YET INCLUDED)

| What | Estimated N | Resolution | Status |
|---|---|---|---|
| Per-bookmaker closing moneylines | ~200K | Game scores (exact) | Needs precomputation — query too slow for web request |

---

## 6. Mistakes & Lessons

| Date | Mistake | Impact | Root cause | Prevention |
|---|---|---|---|---|
| May 19 | Bulk is_winner reset | Golf MCE 4.8pp → 33.3pp, hockey regressed | Reset cleared correctly-resolved markets that Kalshi API had since purged | **Gotcha #83**: Never reset is_winner without confirmed alternative source |
| May 20 | "Kalshi predictions are bad" | Wasted time chasing wrong theory | Didn't look at actual outcome data; assumed calibration = prediction quality | Always check raw data before theorizing |
| May 20 | Ask-price-as-probability | Golf longshots stored at 98% instead of 2% | Polling fallback used yes_ask when yes_bid=0 | Fixed: ask fallback capped at ≤0.50 |
| May 18 | Spreads cover check inverted | 28.6pp MCE on spreads | (margin > spread) wrong for signed home_spread | Fixed: (margin + spread > 0) |
| Pre-session | Odds API moneylines not in calibration | Entire source missing from calibration for months | Nobody checked | Coverage audit endpoint now exists |
| May 21 | Aggressive opening threshold nuked hockey | Hockey regressed 5pp | 70% cap for 20+ outcome markets caught legitimate player props | Pulled back to 50% for 50+ outcomes only, repair step restores from snapshots |

---

## 7. What's NOT in this document yet (needs automated decomposition)

- Exact outcome counts per source × league × market_type × age
- Resolution source breakdown per cell (API vs game_score vs Pass 2 guess)
- Opening probability derivation breakdown
- Forward capture verification per cell
- MCE per cell (only meaningful with authoritative resolution)
- Per-bookmaker moneyline calibration data

These will be populated by the automated decomposition endpoint (Deliverable 2).
