# Interestingness / ranking rules — Alex's taste heuristics (R1–R10)

Provenance manifest for the taste rules Alex gave in the 2026-06-15 label-pass
interview (source: `.claude/handoff/alex_interestingness_heuristics_2026-06-15.md`,
captured after the #596 label session). Each rule is encoded as a **scorer
feature**, a **classifier suppression/boost**, a **display rule**, or **filed**
with a stub metric when it needs a signal we don't have yet.

Every rule carries a **gold assertion**: a labeled example the offline replay
(`scripts/replay_discover_ranking.py`) / classifier tests must keep in or out of
the top-K. Implemented gold assertions live in
`backend/tests/test_feed_quality_alex_rules.py`; filed ones are skipped stubs in
the same file (intent + provenance preserved until the signal lands).

| Rule | One-line | Mechanism | Status | Where |
|------|----------|-----------|--------|-------|
| R1 | Resolved/already-happened ⇒ downrank, UNLESS surprising **and** well-explained | Gate the settled/resolution path on (surprise × explanation quality), not recency | **Filed** — needs a surprise×explanation-quality signal | stub: `test_r1_...` |
| R2 | Asset price-LEVEL markets ("X above $Y" on any stock/crypto/commodity) ⇒ never interesting | Classifier `low_quality` suppression | **Implemented** | `feed_market_quality._is_asset_price_level` |
| R3 | Novel sports framings (nationality/region/aggregate angle) ⇒ interesting; not vanilla props | Classifier `compelling` **boost**, sports-gated | **Implemented** | `feed_market_quality._is_novel_sports_framing` |
| R4 | "Non-intuitable odds" (odds a smart fan couldn't pre-guess) ⇒ boost | Scorer feature (priors-guessability) | **Filed** — needs novel entity-pair / specific-scenario detection | stub: `test_r4_...` |
| R5 | Confirmed positive drivers: real-world story, contested/surprising odds, resolves-soon, marquee entity | Already in scorer + `_COMPELLING_RE` | **Implemented (pre-existing)** | `market_interestingness` signals + `_COMPELLING_RE` |
| R6 | Resolved SPORTS ⇒ never surface (ESPN already gives him scores) | Classifier `suppress` | **Implemented** | `feed_market_quality._is_resolved_sports` |
| R7 | Same-theme markets should be GROUPED into one multi-angle card, not scattered | Product work: multi-angle cards over `group_id`/story_key | **Filed** — product item, bigger than a classifier tweak | stub: `test_r7_...` |
| R8 | "#1 yes, #2 no" — number-one markets eligible; runner-up/#2+ downranked | Classifier `low_quality` | **Implemented** | `feed_market_quality._is_runner_up_rank` |
| R9 | Bare numeric markets (box-office $, critic score) need a frame of reference | Enrichment: comparison/expectation baseline + grouping-for-comparison boost | **Filed** — needs enrichment | stub: `test_r9_...` |
| R10 | Shape is secondary to VISUALIZATION — do NOT suppress threshold ladders by shape | Constraint: no shape-only ladder suppression | **Honored (constraint)** — R2 kills price-LEVEL *content*, not ladder *shape*; heat-strip viz track stands | n/a |

## Verbatim provenance (abridged)

- **R1/R6:** "The only reason I'd want to see a resolved outcome … would be if it
  was a surprising outcome and there was an explanation of what made it
  surprising." (sports scores: he gets those from ESPN.)
- **R2:** picked "All price-level markets out" — any 'X above $Y' on stocks,
  crypto, OR commodities is never interesting. Macro policy/event markets (Fed
  decision, recession y/n, CPI surprise) are a DIFFERENT category and stay
  eligible.
- **R3:** "Unusual futures and props are often interesting, like 'Will a Canadian
  team win the NHL Stanley Cup?' or 'Will a golfer from Europe or from Asia
  finish higher?'"
- **R4:** "if I wouldn't have had intuition about the odds. 'Will Taylor Swift get
  married in Madison Square Garden?' is a market where I couldn't possibly guess
  the odds before I see them."
- **R7:** "I don't like it when I get five different versions of the same war or
  geopolitical theme … if we can group some of those together and show a theme
  from a few different angles, there's potential for that to be valuable."
- **R8:** "which songs/shows/movies/albums will be number one … I see a lot of
  markets … for what will be number two, and that is almost never interesting."
- **R9:** box office / critic scores interesting "if you give me a frame of
  reference."
- **R10:** "A threshold ladder, if we do a really clever visualization, could be
  just as interesting … as a yes-no market."

## Notes on overlap (R2)

R2's asset price-level suppression is intentionally **broader** than the older
named-asset ladders (`_PRICE_BUCKET_RE`, `_COMMODITY_DATED_PRICE_RE`,
`_DATED_FINANCE_METRIC_RE`): it catches single tickers (e.g. `META close above
$700`) via an asset-context ∧ price-threshold match, and it is OR'd into
`price_bucket`. The macro-event carve-out (`_MACRO_EVENT_RE`) keeps Fed/CPI/
recession event markets eligible.
