# US Open (golf major) market coverage — diagnosis & fix plan

**Date:** 2026-06-18 · **Author:** Fable (Cowork) code-path diagnosis, requested by Alex · **Status:** issues drafted below, not yet filed (see note)

> **Method caveat:** Production HTTP (`curl`, `web_fetch`) and `gh` were network-blocked from the session that produced this, and the GitHub integration was read-only (issue creation returned `403 Resource not accessible by integration`). So this is a **code-path diagnosis**, not a live audit. The structural gaps below are facts about the code and hold regardless; the only thing not confirmed live is the exact current state of any single market (e.g. whether the daily LLM pass has already tagged a given series `golf`). A Claude Code session on the host can confirm counts via `db-query`, and can file the issues below via `gh`.

## What the "US Open tournament details page" is

The page is `/categories/golf/tournaments/us-open` (frontend `frontend/app/categories/golf/tournaments/[slug]/page.tsx`), served by **`get_golf_tournament`** (`backend/app/routes/golf.py:1833`) + `GET /api/golf/leaderboard`. It renders a golfer leaderboard grid with **Win / Top 5 / Top 10 / Top 20 / Cut** columns, an evolution chart, a live cut-line "Bubble Watch," and a generic **"More Markets"** list.

Two gates determine whether one of the linked markets reaches the page:

1. **Classification.** The golf query selects `llm_sport_category == 'golf'` (or Odds API `external_id ilike 'golf_%'`) — `golf.py:1263`. For Kalshi this is deterministic only when the ticker prefix is in `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` (`sport_keys.py:951–974`); otherwise it depends on the market name carrying "PGA"/"golf" (men's "U.S. Open" alone is **not** a golf name-rule) or a once-daily LLM reclassification.
2. **Surfacing.** `get_golf_tournament` **ignores** the structured `prop_markets` pipeline that `get_golf` builds and re-derives types with the coarse `_detect_market_type` (`golf.py:1699`), which only recognizes **6 types**: winner, top_5, top_10, top_20, make_cut, round_leader. Everything else collapses to `"other"` → the "More Markets" dump. Binary yes/no markets with ≤2 outcomes are dropped at `golf.py:1345–1348` before they can become a prop.

## Per-market status

| Market (source) | Gathered as golf? | Grouped to US Open? | Surfaced? | Root cause |
|---|---|---|---|---|
| Tournament winner / competitors (Kalshi `kxpgatour`) | yes (mapped) | yes | yes (winner field) | — |
| US Open winner (Polymarket, "us open"-named) | yes (golf tag) | yes | yes (merges w/ Kalshi) | — |
| Round 1/2/3 leader (Kalshi `kxpgar{1,2,3}lead`) | yes (mapped) | yes | **no** — computed, no grid column | Issue C |
| Top 5/10/20 (Kalshi `kxpgatop{5,10,20}`) | yes (mapped) | yes | yes (grid columns) | — |
| Top 40 (Kalshi `kxpgatop40`) | maybe (not mapped) | maybe | **no** | Issues A + C (no `top_40` type) |
| Round 2/3 Top 5/10 (Kalshi `kxpgar{2,3}top{5,10}`) | yes (mapped) | yes | **no — corrupts** real Top 5/10 | Issue C (regex collision) |
| Lowest-round / round / hole score (`kxpgaroundlow`, `kxpgaroundscore`, `kxpgaholescore`) | maybe (not mapped) | maybe | **no** | Issues A + C |
| Stroke margin (`kxpgastrokemargin`) | maybe (not mapped) | maybe | raw dump only | Issues A + C |
| Albatross (`kxpgaalbatross`) | maybe (not mapped) | maybe | **no** | Issues A + D (yes/no drop) |
| Player category USA/APAC/EUR/LIV (`kxpgaplayercat`) | maybe (not mapped) | maybe | **no** | Issues A + C (regions stripped) |
| Matchups / 3-ball (Kalshi `kxpgah2h` + 3-ball) | h2h yes; 3-ball maybe | yes | **no — built but never rendered** | Issues A + C (no UI) |
| Polymarket "**uptspt** open" props (FRL/SRL/TRL, first-time winner, best round, playoff, make cut, league of winner, hole-in-one, nationality, record-low round) | yes (if golf-tagged) | **no — orphan card** | mostly no | Issues B + D |

## Four root causes → four issues

### Issue A (quick win #1) — Kalshi US Open prop series missing from the ticker map
`KALSHI_FUTURES_TICKER_TO_SPORT_KEY` (`sport_keys.py:951–974`) is missing `kxpgaroundscore`, `kxpgaroundlow`, `kxpgatop40`, `kxpgaplayercat`, `kxpgaholescore`, `kxpgastrokemargin`, `kxpgaalbatross`, and the 3-ball/matchup prefixes. Kalshi ingest (`tasks/kalshi.py:202–292`) has no LLM at ingest, and men's "U.S. Open" is not a golf name-rule (`futures_categorization.py` golf patterns ~82–85), so these can sit `'other'` (invisible) until the 8 AM UTC `recategorize_other_task` LLM pass. **Fix:** add the prefixes (verify exact tickers vs the live Kalshi API) + add a men's-major golf name-rule. No migration. Labels: `area:event-details`, `type:bug`, `priority:p1`, `needs-agent`.

### Issue B (quick win #2) — Polymarket "uptspt open" scramble orphans US Open events
Polymarket obfuscates the trademark ("2026 uptspt Open …"). `_normalize_tournament` (`golf.py:776–822`) matches the US Open only via `r"us\s+open|u\.s\.\s+open"` (`golf.py:153`); the DataGolf fuzzy fallback needs ≥2 shared words and "uptspt open" shares only "open," so these form a separate "Uptspt Open" card. **Fix:** normalize scrambled major names → canonical before `_normalize_tournament` (map "uptspt open" → "us open"; check the other majors too) or add an alternation at `golf.py:153`. Labels: `area:event-details`, `type:bug`, `priority:p1`, `needs-agent`.

### Issue C — detail page surfaces only 6 market types
`get_golf_tournament` (`golf.py:1833`) ignores `prop_markets` and uses the coarse `_detect_market_type`. Consequences: round leaders enriched but no column (`golf.py:1987`); Round-2/3 Top-N mis-bucketed into and corrupting tournament Top-N (`\bTop\s+5/10\b` has no "Round N" boundary, averaged at `golf.py:1973`); Top-40 unsupported; player-category regions stripped by `_PROP_OUTCOME_RE`; scores/margin/nationality only as raw "More Markets" rows; `h2h_matchups` returned (`golf.py:2054`) but never rendered by the frontend. **Fix:** rework the endpoint to consume structured/grouped prop data and add frontend sections (round-leader columns or rounds panel, Top-40, score/margin/category props, H2H section); fix the Round-N Top-N regex collision. Natural home for a reusable major-event layout. Labels: `area:event-details`, `type:quality`, `priority:p2`, `needs-agent`.

### Issue D — binary yes/no golf props dropped before surfacing
`golf.py:1345–1348` skips non-winner yes/no markets with ≤2 outcomes; `_extract_prop_market` strips `^yes$/^no$` and returns None (`golf.py:222`, `:933`). Kills albatross, hole-in-one, playoff, first-time winner, record-low-round. **Fix:** surface yes/no props as a single-probability prop ("Hole-in-one: 38% Yes"). Do alongside Issue C. Labels: `area:event-details`, `type:bug`, `priority:p2`, `needs-agent`.

## Strategic vision — auto major-event dashboard
The end state Alex wants: for major events (golf majors, Oscars, Super Bowl, etc.), auto-generate a beautifully formatted dashboard that gathers and groups every related market. Issues A–D are the prerequisite baseline for golf majors: A/B make the markets reliably *gathered & grouped*; C/D make them *render in a grouped, typed layout* — which is the reusable template the dashboard generator would extend. Track as a strategic backlog item (`[idea]`) once A–D land.

---

## Filing note
These were not filed automatically (GitHub integration was read-only this session). To file from a host Claude Code session: `gh issue create --title "…" --label area:event-details --label type:bug --label priority:p1 --label needs-agent --body "…"` for each of A–D (full bodies above). Recommended order per Alex: **A and B first** (quick, deterministic, low-risk), then C + D together.
