# Gotchas & Tips (Extended Reference)

The top 15 gotchas are in CLAUDE.md. This file contains the full list for deep-dive reference.

---

## Items 16-39 (overflow from CLAUDE.md)

16. **Deleting events requires FK cleanup** — must delete from 8+ tables before removing the event row. Use raw SQL, not ORM `db.delete()`, to avoid autoflush FK violations.
17. **Kalshi auto-creates pm_ events** when no matching event exists. Guard added to prevent new duplicates, but historical orphans need cleanup via admin endpoints.
18. **Quota guard expiry date** must be updated monthly in `redis_state.py` (`QUOTA_GUARD_EXPIRY`).
19. **Name normalization** — ALL team name matching goes through `utils/name_normalization.py`. City abbreviations (LA->Los Angeles, NY->New York, etc.) are expanded before token overlap scoring.
20. **Championship grid data quality** — Kalshi 0.45-0.65 noise filter, monotonicity enforcement (P(round N) >= P(round N+1)), esports "Masters" pattern can leak into golf.
21. **Frontend-only changes don't need Heroku push** — Only `git push origin master` needed. Vercel auto-deploys. Heroku push is only required when backend code changes.
22. **Never show 100%/0% probabilities for finished events** — Post-game completion probabilities (winner=100%) must be filtered. Use opening odds or aggregate probability instead.
23. **Chart domain must derive from game timeline** — Use `commenceTime` + last ESPN/score data timestamp. Never constrain chart domain solely from odds data (which may be sparse during API outages).
24. **`classifyPlayoffStage()` order matters** — Conference patterns must be checked BEFORE championship patterns in `RelatedFutures.tsx`. "Eastern Conference Champion" contains "champion" and will misclassify as "Championship" if checked in wrong order.
25. **`compute_aggregate_probability()` is the single source of truth** — Both feed API and event detail API must use it. Never display raw odds_snapshots without aggregate fallback.
26. **Bash heredocs with Python** — When piping Python code via bash, use `python3 << 'PYEOF'` (quoted heredoc) to prevent shell variable expansion and `!=` escaping issues.
27. **Golf market filtering** — `_NON_WINNER_MARKET_RE` in `routes/golf.py` filters out "compete in", "make the cut", "top N finishers" etc. from headline probabilities. Only outright winner/champion markets should appear in card hero probabilities.
28. **Evolution chart position/stage pills** — `EvolutionView.tsx` supports `positionOptions` prop for switching markets. Golf uses Top 20/10/5/Win from Kalshi. Team sports use grid column market_ids (Make Playoffs/Conference/Championship). Pass `entityLabel="Teams"` for team sports.
29. **Golf tour classification** — Many events are mislabeled as "PGA Tour" when they're DP World Tour, Asian Tour, etc. DataGolf provides the correct `tour` field. Fix needed.
30. **Golf "LIVE" badge** — `isTournamentLive()` in the tournament page now has date-based validation (added April 14). Tournaments past their `end_date + 1 day` can't be "live". Also checks `schedule_status === "completed"` before falling back to leaderboard status.
31. **Men's/women's golf major separation** — `_normalize_tournament()` returns the same key for both. The grouping loop in `golf.py` appends `_womens` suffix when `_WOMENS_RE` matches the market name. `TOURNAMENT_DISPLAY_NAMES` and `TOURNAMENT_ORDER` have entries for both variants.
32. **Championship grid inline data bars** — `TournamentProgressionTable.tsx` uses sqrt-scaled horizontal bars instead of background color heat maps. Bar width = `sqrt(prob) / sqrt(0.4) * 100%`. Font weight varies: semibold >10%, normal 1-10%, faded <1%.
33. **Evolution chart SWR caching** — 7d/24h/today share the same SWR cache key (same fetched data, filtered client-side). Only "Season" triggers a separate fetch (4320h). `keepPreviousData: true` prevents blank during re-fetch.
34. **Grid columns include market_id** — `playoffs.py` returns `market_id` on each column (most common market_id from that column's data). Frontend uses these to build stage pills for the evolution chart.
35. **Cup card detection** — `TournamentCard.tsx:_isCupEvent()` checks tournament key for ryder/presidents/walker/solheim. When a cup has exactly 2 golfers (teams), renders `CupCard` with left/right layout + probability bar instead of leader/chasers.
36. **Python 3.12+ redundant imports cause UnboundLocalError** — `from datetime import timedelta` inside a function body makes `timedelta` local to the ENTIRE function scope. If the function uses `timedelta` before that line (from the module-level import), it crashes. Fixed in `espn_sync.py` April 15. Check for this pattern in other files.
37. **Related Futures requires Kalshi ticker prefix matching** — Kalshi futures tickers (KXNBA, KXMLB, etc.) don't start with the Odds API sport key (basketball_nba, baseball_mlb). The sport filter in `get_related_futures()` needs `_SPORT_TO_KALSHI_ROOTS` to find championship/award markets. Without this, only game-level Kalshi markets (which DO have sport-key external_ids) are discoverable.
38. **`FuturesMarket.market_tier` is NULL for most markets** — The `market_tier` field was designed to filter championships (1) from game props (5), but most markets have NULL. This prevents efficient querying for Related Futures. Fix: populate tier during Kalshi/Polymarket task upserts using `MarketMatchingRule` from `league_configs.py`.
39. **Team model uses `logo_url_small` not `logo_small`** — The column name is `logo_url_small` (and `logo_url` for full size). Using `Team.logo_small` crashes with AttributeError.


40. **Polymarket neg-risk markets need bid/ask fallback** — The Gamma API bulk `/events` endpoint returns `outcomePrices` as null for neg-risk multi-outcome markets (championships, conference winners). The poller must fall back to `bestBid`/`bestAsk` midpoint or `lastTradePrice`. Without this, all championship/conference outcome probabilities are 0%.

41. **Play-in ≠ Make Playoffs** — Kalshi's "Teams to Make the Eastern Conference Play-In Tournament" contains "Eastern Conference" but is NOT a conference championship market. Top seeds have ~0% play-in probability but ~99% playoff probability. Play-in markets must be excluded from the grid entirely (return `None` from `_match_market_to_column`), not routed to make_playoffs.

42. **Odds API score fetching is partially redundant** — ESPN provides scores every 60s for mapped sports (NBA, NHL, MLB, NFL). The Odds API `/scores` endpoint is only needed for non-ESPN sports (tennis, cricket, rugby). Score fetching is now skipped for ESPN-mapped sports where all recent events have `espn_event_id`.

43. **Admin daily burn chart uses two counting systems** — The official count (`x-requests-used` header) and the per-task incremental tracking can diverge. The chart scales task proportions to match the official total to prevent retroactive shrinking.

44. **EOM quota forecast must exclude today's partial day** — Using today's incomplete data in the trailing average makes the forecast artificially optimistic as the day progresses. Always use the two most recent *complete* days.

45. **Polymarket game events have nested sub-markets** — A single Polymarket "event" (e.g., "Magic vs Pistons") contains ~40 sub-markets (moneyline, spread, O/U, player props). These are NOT outcomes of one market — each sub-market has its own `condition_id` and `question`. The polling task must create separate FuturesMarket rows per sub-market, not flatten them into outcomes. NegRisk events (championships, multi-candidate) are different — each sub-market IS one candidate and correctly maps to outcomes.

46. **ORM attribute assignment lost when mixed with Core SQL updates** — Setting `event.field = value` via ORM, then doing `session.execute(update(Event).where(...).values(...))` via Core SQL in the same session can cause the ORM change to silently not persist. Found 3 times: `espn_id` (varchar), `box_score_data` (JSONB), and the original `win_probability_sources` (JSONB, gotcha #8). **Safe pattern for Celery tasks:** use Core SQL (or raw text SQL) for ALL writes, then sync the ORM object afterward (`event.field = value`) to prevent the ORM flush from reverting the DB state. For JSONB specifically, raw text SQL with `cast(:val AS jsonb)` is most reliable.

48. **`box_score_data` must be exposed in the event detail API** — The `GET /api/events/{id}` response must include `box_score_data` for the frontend `PlayerPropsDashboard` to show actual stats on completed games. Without it, the component falls back to "pre" mode (showing probabilities). The related-futures endpoint already used `box_score_data` internally but the event detail endpoint did not return it until April 30, 2026.

47. **Admin auth env var is `ADMIN_TOKEN`, not `ADMIN_SECRET`** — Heroku has `ADMIN_TOKEN` set. The code checks `ADMIN_TOKEN` first, with `ADMIN_SECRET` as fallback. When referencing the admin secret in code, documentation, or curl commands, use `ADMIN_TOKEN`. This mismatch caused a production lockout on April 21, 2026 when a security fix defaulted to False on missing `ADMIN_SECRET` (which was never set — only `ADMIN_TOKEN` existed).
