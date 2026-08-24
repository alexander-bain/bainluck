# CLAUDE.md overflow archive — 2026-08-24

Archive of text trimmed from CLAUDE.md 2026-08-24. Nothing here is canonical; canonical homes are
`docs/gotchas-reference.md`, `docs/rulings/*`, `docs/architecture-reference.md`. Kept so the trim
provably deleted nothing.

Every block below was extracted **mechanically** from `git show HEAD:CLAUDE.md` at
`b5c2a750` (the 72,635-char file the trim replaced) by line range — no line in this file was
retyped. The captions and this header are the only authored text.

The trim was forced by the 40,000-character tool read limit: at 72.6k, every lane was reading
CLAUDE.md **silently truncated**, losing the tail of the file — including the credential rule and
the Quick Reference table — with no error and no signal that anything was missing.

---

## Semantic Matching — the 2026-07-14 freshness note

*Trimmed from the `## The #1 Technical Challenge: Semantic Matching` section. The replacement keeps the one-sentence version (April-24 audit, `--self-check` schema-stale, #193); the three compounding reasons and the July spot-check measurements are here.*

**Freshness note (re-measure attempted 2026-07-14, docs-sweep Queue #192):** the table's last FULL audit is still April 24 — a clean full re-measure could not be produced today for three compounding reasons, so the April-24 column is intentionally left in place rather than overwritten with tooling-limited numbers:
1. **`--self-check` is schema-stale.** The Discover feed moved to a nested `items[].data` shape with a `type` field (`event`/`futures`/`tournament`/`concept`) and top-level `sport=null`; the script still reads the old flat schema, so it sees `sport=""` on every card and renders `? @ ?`. Fixing the feed parser is queued for the next code queue (#193).
2. **`audit_grid_accuracy.py` needs an external `--ground-truth` file** — it is not a standalone self-check, so it can't be run fresh here. (It was Manus-fed; Manus is permanently retired as of 2026-07-31, so this path is dead until the C96 replacement rail lands.)
3. **Mid-July is an off-brand sports lull.** Today's feed-surfaced game slate is NBA Summer League, NPB, UCL qualifiers, World Cup, and one settled MLB game — no Tier-1 games, and thin upstream Kalshi/Polymarket game-market coverage.

Direct production spot-check of the 13 feed-surfaced game events (via `/api/events/{id}/game-markets` + `/related-futures`): **L1 = 13/13** (every game carries ≥1 win-prob source); **L2 = 0** game markets (expected upstream coverage gap for this off-brand slate — not a matching regression); **L3 verified working** (e.g. Red Sox @ Rays surfaces 6 team futures). A true dated L1–L4 column requires fixing the self-check feed parser (#193) and re-running during an in-season Tier-1 slate. Also spot-verified July 14: duplicate events = 0 (#1085 fixed, sentinel-guarded), The Open round-leader dates correct (#1088), kalshi calibration ECE ≈ 1.0pp. The **Flow Sentinel** (`backend/app/tasks/flow_sentinel.py`, nightly 07:10 UTC; `POST /api/admin/flow-sentinel/run`, `GET .../flow-sentinel/last`) regression-guards the user-facing half of this table and auto-files evidence-packed issues (GITHUB_TOKEN rail live).

---

## Tech Stack — the long iOS/watchOS/widget row

*Trimmed from the `## Tech Stack` table. The replacement keeps the load-bearing rule (synchronized groups ⇒ filesystem presence IS target membership; widget wired, complication not); the full P7 Step-0 audit prose is here.*

| iOS / iPadOS / macOS / watchOS App | SwiftUI (shared codebase, 142 Swift files across app/watch/widget targets — 129 main app, 9 watchOS, 4 widget). The Apple Watch app exists today and is the top-priority secondary surface (P7). Caveat surfaced by the P7 Step-0 audit (#1080), **half-corrected 2026-08-11**: the watch app builds & ships; the **widget IS wired** — the project is `objectVersion = 77` using Xcode 16 file-system-synchronized groups, and `BainLuckWidget` is a native target with its folder synchronized into it (`target 'BainLuckWidget' <- ['BainLuckWidget']`), so `BainLuckWidget/*.swift` compiles today. The **watch complication is still unwired** (`BainLuckComplication` is a target but has no `fileSystemSynchronizedGroups` entry). Under synchronized groups, filesystem presence IS target membership — so "is it in a Sources build phase" is the wrong question to ask of this project (there are none). | TestFlight / direct |

---

## Discover Feed Ranking & Explanation Pipeline — full subsection

*Trimmed from `## Core Architecture`. The replacement keeps the operating rules that must not regress; the full constant tables, penalty values, and allowlist detail are here. Canonical home going forward: `docs/architecture-reference.md`.*

**Discover Feed Ranking & Explanation Pipeline** (`routes/feed.py`, `utils/feed_market_quality.py`, `utils/feed_reasons.py`, `scripts/audit_feed_quality.py`):
- The feed builds multiple candidate pools (sports, non-sports volume, movement, enriched, soon-resolving), scores with futures highlights, then applies market-quality caps/diversity before returning cards.
- Quality classifier suppresses narrow commodity/finance ladders, repetitive dated buckets, social-count filler, and weak explanation cards. It separately boosts compelling public stories: politics, geopolitics, Fed/economics, AI/tech, health outbreaks, entertainment, and sports personnel.
- Deterministic futures explanations are now first-class. Do not rely on LLM hooks to make the first page understandable: headlines should name the mover/leader/source disagreement from existing outcome data (e.g., "Yes side up 32.5 points from opening").
- Personalization is intentionally bounded and latency-safe: recent Discover interactions produce small category plus feature/entity/archetype affinities for signed-in users and anonymous sessions. Right swipe is `like` / "more like this"; left swipe is `unlike` / "less like this" and should be treated as a soft downrank, not a permanent hard dismissal. Category dismiss penalty escalates: 3+ swipes -> -0.40 (0.60x), 5+ -> -0.60 (0.40x), 8+ -> -0.80 (0.20x). Feature dislike penalty caps at -0.25. Semantic dismiss propagation compares candidate topic/region/team/term tokens against the 50 most recent dismiss/unlike token sets, ignores generic category/type/archetype/format overlap, and applies only a soft `semantic_dismiss:-0.30` multiplier penalty above 0.60 Jaccard similarity. `MIN_MULTIPLIER` is 0.15.
- Dismiss signal propagates to story keys and group IDs: dismissing one "Will Russia capture [village]?" market suppresses all markets sharing the same `story:russia_ukraine` key. `recent_dismissed_story_keys` and `recent_dismissed_group_ids` are populated during personalization context loading.
- Discover event demotion in Discover mode (`event_pct < 0.3`): non-exceptional events are capped at score 35 so futures can compete. "Exceptional" requires (see `_is_discover_event_demotion_exception` in `feed.py`): EI >= 85 (any league), EI >= 80 AND Tier 1/2 league, high-drama headline keywords ("elimination"/"buzzer"/"walk-off"/"historic") AND Tier 1/2 league, or postseason keywords ("playoff"/"championship"/"finals") AND Tier 1/2 AND EI >= 60. ALL drama/postseason keywords require major-league context — none are tier-free.
- Election allowlist: `_MAJOR_ELECTION_RE` in `futures_highlights.py` matches major-country and US political keywords (defined at `:319–329`; note: an earlier stricter definition at `:199–219` is dead code, overridden by the later redefinition). Elections with "election/winner/nominee" that don't match get `FOREIGN_LOCAL_ELECTION_PENALTY = -30`. Obscure elections (UK boroughs, by-elections) get a separate `-20` penalty via `_OBSCURE_ELECTION_PATTERNS`.
- Soccer league allowlist: `_TOP_TIER_SOCCER_RE` in `feed_market_quality.py` matches EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, Europa League, MLS, FIFA World Cup, Copa America, Copa Libertadores, Liga MX. Non-matching soccer futures get `story:minor_soccer_leagues` (capped at 1).
- Geopolitics story caps: `story:russia_ukraine` (cap 2) now catches Russia + capture/enter/advance/territory AND Russia + Putin/president/regime/fall. `story:middle_east_conflict` (cap 4) catches Iran/Israel/Gaza/Hormuz.
- Category base scores are defined in `CATEGORY_BASE_SCORES` (`futures_highlights.py:87–97`): politics 45, geopolitics 45, economics 42, tech 42, entertainment 40, culture 38, health 38, weather 32, crypto 28. Sports get `SPORTS_CATEGORY_BASE = 18.5`. Entertainment has dedicated compelling patterns for awards shows, TV series, and media platforms.
- LLM enrichment is intentionally bounded and async. `enrich_market_hooks` only targets feed-shaped candidates and Celery runs small batches (`limit=100` every 6h). `enrich_discover_llm_metadata` adds cached structured metadata under `FuturesMarket.market_metadata["discover_llm"]` for feed-shaped candidates (`limit=125` every 6h), and feed ranking consumes only that cached metadata. Never run LLM calls inside `GET /api/feed` or grind through the full open-market backlog (~56K markets).
- Daily LLM eval is advisory only: `evaluate_discover_with_llm` grades the top 50 Discover futures, compares against Polymarket email highlights, and writes `llm_proposed_*` review rows for admin inspection. These rows do not affect ranking unless a human later records an accepted promote/downrank decision.
- Interestingness scoring: `precompute_interestingness` runs every 2h (`tasks/__init__.py`), caches per-market scores in Redis, and `_score_futures` blends them into feed ranking at 20% weight (controllable via Redis key `interestingness:blend_weight`, default 0.2, kill switch at 0). The blend is capped at `pre_blend + 15` to limit uplift. The pure scorer lives in `utils/market_interestingness.py`; `scripts/calibrate_interestingness.py` supports offline weight tuning against labeled data. Note: the blend weights have not yet been calibrated against labeled data — that calibration is tracked as a separate work item.
- Current production audit target: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20`. Use `python3 scripts/audit_feed_quality.py` to measure.

---

## Gotchas Hot List — full prose of the trimmed entries

*The Hot List in the replacement carries the RULE for each of these; the incident, the measurements, and the amendments are here. Canonical home: `docs/gotchas-reference.md`.*


### 10 — build is the ESLint gate, typecheck is the TS gate

10. **`npm run build` is the ESLint gate, NOT a TypeScript gate — `npm run typecheck` is the TS gate, and it IS a deploy gate.** `next.config.mjs` still sets `typescript.ignoreBuildErrors: true`, so `next build` deploy-blocks on ESLint/rules-of-hooks failures but **passes through TS type errors**. Since L2-234 that no longer means type errors ship: CI runs a separate `Type check (fail-on-new)` step (`npm run typecheck` → `scripts/tsc-census.js --run --check`) **after** the build — deliberately after, because `.next/types/**` is generated route typing that tsconfig includes. It is a **ratchet, not a clean gate**: pre-existing errors are recorded per file in `frontend/typecheck-baseline.json` (owned by #1521) and do not fail; **one more than the baseline fails, and one FEWER also fails** (fix an error → lower the baseline, or the recorded count drifts above the real one and becomes silent headroom). Run `npm run typecheck` locally before pushing, not bare `tsc --noEmit`. No `continue-on-error`; `frontend/__tests__/lib/ciTypecheckGate.test.ts` plus an e2e-contract workflow-shape fixture assert the step can't be deleted or defanged. (Flipping `ignoreBuildErrors` to false remains an unmade infra decision — the ratchet is what enforces types today.)

### 32 — registry structured match + ruling 048 (with both amendments)

32. **Event Registry structured match MUST include completed/closed status — AND is reachable only for an ID-ANCHORED claim (AMENDED 2026-08-14 by ruling 048).** The status filter on Step 3 must be `IN ('scheduled', 'live', 'completed', 'closed')`, not just scheduled+live: if completed events are excluded, any source that polls after game end creates orphaned duplicates instead of merging (this caused 98% of MLB/NBA/NHL events to have no Odds API data for weeks, May 2026). **But the status filter is now the smaller half of this entry.** `docs/rulings/048-an-id-less-claim-never-absorbs.md` amends the absorption behaviour itself: **an id-less claim NEVER absorbs — it creates.** Step 3 requires an id-anchored correspondence, in exactly two arms: (A) a **shared** provider id already on the candidate, or (B) the claim's own id **dereferences via its own provider's schedule** to the teams and date it presents (`EventClaim.schedule_derived` — this is the legitimate ESPN-finds-the-Odds-row join). Neither arm ⇒ CREATE, with provenance tagged on the row, and id-keyed reconciliation drains the duplicate when an id arrives. **Do not "restore" absorption-on-name-and-time by citing the first sentence of this gotcha.** Five certification rounds (C-CERT-1801-R1..R4) each moved a threshold inside that design and each produced a new specimen class; the deleted path is a deleted defect, not a regression. Duplicates going up is the declared cost — a duplicate is visible and reversible, a wrong absorption is neither (#1779/#1798: 5,142 / 540 / 2,097 rows of one game's data blended onto another's). The merge task's SQL also needs swapped home/away and normalized name matching — and, since ruling 048, the same id-anchoring on the drain, because it DELETEs the loser.

**AMENDED 2026-08-20 (Alex, RULINGS-NEEDED item 12): the cost is declared and REAL, not declared and BOUNDED — do not teach the old cost model.** Ruling 048 bounds the duplicate with one clause: *"id-keyed reconciliation drains the duplicate when an id arrives."* Measured over the whole population (2026-08-20): **`AWAITING_ANCHOR` = 0 of 74,181 rows**, with 99.61% sitting in `NO_ANCHOR_CHANNEL` — the creating provider has no id column on `events` at all (`kalshi` 73,678 / `polymarket` 503, against exactly three id columns: `external_id`, `espn_id`, `statpal_fixture_id`). Not a lagging drain — a **structurally unreachable** one, for essentially the entire population it bills. A deferred drain and an impossible drain report the same number today and opposite futures (gotcha #53 again). **Alex ruled OPTION A: build the channel** — `event_provider_anchors` per `docs/event-provider-anchor-channel-1946.md`, Kalshi-first, `id_kind='game'` gating identity so prop tickers never absorb. **Option C (loosen absorption back toward name-and-time) is REJECTED explicitly: we do not trade visible duplicates for invisible missing rows.** Until the table ships, the bounding clause is unexecutable prose — cite it as an intention, not a guarantee, and report channel-less rows as `NO_ANCHOR_CHANNEL`, never `AWAITING_ANCHOR`. Amendment note lives in ruling 048's own file.

### 35 — Kalshi retention is measured, not prose

35. **Kalshi EVENT data is permanent but MARKET data is not — retention is >=74 and <86 days (MEASURED 2026-08-07)** — `GET /events/{ticker}` returns the event at any age (`found=True`), but `markets: []` (empty) past the cliff, so the `result` field goes with them (measured: events settled 154d/147d/87d ago return 200 with ZERO markets; a 41d event returns 6 with results intact). `GET /markets/{ticker}` 404s for the same old markets, while `GET /markets/trades` and the batch candlesticks endpoint return **200 with an empty list** — see #51. The settled-events pagination (`GET /events?status=settled&series_ticker=X`) is far shallower than the cliff (KXNBAPTS reached back only 74 days), so old tickers are only probeable from tickers we already hold. **The range is now dated and re-measurable:** `python3 scripts/probe_kalshi_retention.py` (public API, no key, no DB) prints both bounds; the constant it validates is `app/utils/kalshi_retention.py`. Use the constant, never a hand-rolled day count. CAL-P008 found the undated "~2-3 months" version unusable in practice: three separate recovery rails were written by people who cited this gotcha, and every one of them still ground purged markets, because a predicate cannot consume a range written in prose.

### 38 — json.loads holds the GIL for the entire parse

38. **`json.loads` (stdlib C decoder) holds the GIL for the ENTIRE parse** — wrapping a huge `response.json()` in `asyncio.to_thread` does NOT free the event loop, because the C json parser never releases the GIL. A 200-event Kalshi nested-markets page held the GIL ~67s inside the thread, freezing the loop so no `wait_for`/deadline timer could fire → the poll SIGKILLed before creating anything (the 29-day #995 creation freeze; 7 attempts). Fixes: **orjson** (`orjson.loads`, ~5-10× faster = a fraction of the GIL hold; behind an ImportError→json fallback), **smaller pages** (limit 200→50 so each decode is sub-second), and a **resumable cursor** so partial progress persists. Pure-Python work (object construction) DOES release the GIL (~5ms switch interval), so `to_thread` helps there — but never for a giant C-level decode.

### 41 — ordering is never the whole answer

41. **Bulk backfills ordered newest-first can never reach the old tail** — 450K+ newer rows starve a bounded run before it reaches what needs fixing. Old-tail work needs oldest-first ordering or an explicit filter (the combat-wps lesson). **AND THE INVERSE (CAL-P009):** when the backlog EXPIRES, oldest-first without a floor is just as fatal — it processes the already-dead first and never reaches the dying. Queue #152 inverted a sort to oldest-first specifically "so the drain harvests the 2-3mo EDGE cohort before it crosses the cliff", and thereby guaranteed the edge was never reached, because ~150K permanently-purged rows sat ahead of it. A sweep over an expiring population needs BOTH bounds: oldest-first *within* a floor. Ordering is never the whole answer — ask what the ordering starts on.

### 44 — a test anchor must not branch on the clock

44. **A test anchor must not branch on the clock — and "seed at a fixed hour" is what caused the last three instances** — `datetime.now(tz).replace(hour=12)` pins an *hour*, not an *age*, so the age swings a full 24h with the wall clock: it can sit in the FUTURE, and an `if anchor > now: anchor -= 1 day` patch only moves the boundary (the phantom-midpoint suite was red every evening, was "fixed", then went red every afternoon). **Offset FIRST, then truncate** — `(now - timedelta(days=2)).replace(minute=0, ...)`. Better still, **freeze the clock out of the test** when the fixture carries dates of its own: production rows titled "Week of August 3 2026" expire against `market_staleness`, so every *relative* anchor was picking a date to die on. If your anchor contains an `if`, you have not fixed this. Prove it with `backend/scripts/clock_sweep.py <target>` — 12 faked wall clocks, including +400d; it found the fourth instance. (Queue 329, #1729.)

### 48 — non-detached heroku run silently fails

48. **Non-detached `heroku run` silently fails in the sandbox** — an interactive/non-detached `heroku run ...` aborts on an EPERM rendezvous and never executes the command (it is NOT just a log-capture issue). Use `heroku run:detached` and verify side effects via endpoints/db-query ~60s later, never trust the (empty) stdout. (#231/#232.)

### 49 — Sentry issue count is LIFETIME

49. **Sentry issue `count` is LIFETIME, not recent** — the `count` field on a Sentry issue is its all-time event total; a stale/dormant bug can show thousands there while firing zero in the last 24h. Always read the 24h stats buckets (`?statsPeriod=24h` / `stats` on the issue) before triaging by volume — the r236 "2,585 events" alarm on `datagolf_freshness` was a dormant bug's lifetime count.

### 50 — headless xcodebuild and the #Preview macro sandbox

50. **Headless `xcodebuild` fails on SwiftUI `#Preview` macro expansion in a sandbox** — a headless/agent `xcodebuild ... build` aborts during Swift macro expansion with a nested `sandbox_apply` failure (the macro plugin process can't spawn its own sandbox inside the already-sandboxed build). `-skipMacroValidation` does NOT fix it (that skips validation, not the sandboxed expansion). The fix is to disable the compiler's macro sandbox: add `OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'` to the build invocation. Do NOT nuke the SPM cache (`~/Library/Caches/org.swift.swiftpm`, `.build`, DerivedData) trying to "clear" it — in sandboxed envs the re-resolve then fails on network/FS restrictions and you lose the working cache. (L2-165's find; saves every future iOS queue a cycle.)

### 51 — every git verb takes -C (three amendments)

51. **Destructive git takes `-C`** — in any multi-worktree session, `reset`/`checkout`/`clean`/`rebase` MUST use the explicit `git -C <path> …` form. A bare invocation relies on an inherited cwd, which is *session* state set by some earlier call — often one issued in the same parallel block, where ordering isn't guaranteed — so the directory it lands in is invisible in the command itself. This is the WRITE-direction twin of #47. Named failure 2026-08-07: a `cd`-less `git reset --hard origin/master` inherited a `cd ~/bainluck` from its own tool block and reset the shared MASTER worktree instead of the program worktree. Commits came back from the reflog; **nine files of uncommitted work were gone permanently** — unstaged content has no git object, so reflog/`fsck`/`lost-found` have nothing to return (#1575). **AMENDED 2026-08-10 (Fable): WRITE-shaped verbs join the destructive ones.** `add`/`commit`/`branch`/`stash` also take `-C`, because a *successful* commit into another lane's branch is HARDER to notice than a destructive failure: nothing errors, nothing is lost, and the work simply appears somewhere nobody is looking — surfacing later as a mystery passenger on someone else's push (see ruling 023, six codex passengers in one day). A destructive command that lands in the wrong tree at least announces itself. Near-miss: CAL-P031's compound `add`/`commit` ran against INT-036's dirty branch (verified clean afterwards, but only because someone checked). **AMENDED 2026-08-14 (Alex, ruling 056): `-C` pins the DIRECTORY, not the BRANCH — and this gotcha has never covered the second question.** Two mirror incidents in `~/bainluck` minutes apart on 2026-08-14 both satisfied every word above, because `-C ~/bainluck` was the *correct directory* both times; the tree was on the wrong *branch*. (A) queue 352's R5 work — 11 files, ~650 lines — was committed onto `master` as `f23cd218` and rescued only because the commit existed before the `reset` ran; reverse that order and it is #1575 again, unrecoverably. (B) the `program/calibration-50` merge was made while the tree sat on `lane1/q352`, producing `4852f46c`, which is contained in **no branch** and survives only in the reflog. A path cannot carry a ref, so no flag closes this: the fix is the invariant that **`~/bainluck` is always on `master`**, branch work happens only in per-queue worktrees, and master-writes only in the Integrator's dedicated detached worktree. Before any `commit`/`merge`/`reset` in a shared tree, check the branch too — `git -C <path> rev-parse --abbrev-ref HEAD` is one call, and it is the call neither incident made.

### 52 — no orphan WIP in the shared master tree

52. **No orphan WIP in the shared master tree** — uncommitted changes in `~/bainluck` must be committed to a named branch or stashed-with-message within the session that made them; the Integrator commits anything dirty >24h to a `rescue/<date>` branch at Phase 0. Orphan WIP is not neutral parking: it taxes every integration (each one must prove its diff is disjoint from files no one owns) while being one wrong command away from deletion. Never reconstruct lost work by archaeology — re-do it from intent in a scoped queue, or rule it unneeded (#1575).

### 53 — an empty 200 is a response shape

53. **An empty 200 is not an absence — it is a response shape** — when an API returns the same body for "this never existed" and "there is nothing to report", any code that infers a FACT from the emptier reading is inventing it. Kalshi's `GET /markets/trades` answers **HTTP 200 with `trades: []`** for a purged market exactly as it does for a real market that never traded; `GET /events/{ticker}` likewise answers 200 with `markets: []` rather than 404. The trade backfill therefore could not tell "no pre-game trading happened" (a fact about the market) from "Kalshi deleted this" (a fact about retention) — and a run that recovered nothing at all looked identical to a run with nothing to do: 500 fetched, 500 empty, 0 created, recorded as a SUCCESS every 6h for ten weeks while #683 sat open as a P0. **Disambiguate with a second signal before writing any claim:** the existence lookup, the age against a measured retention bound (#35), or an explicit sentinel value. And make the zero-yield case loud — see `app/utils/task_verdict.py`, whose whole purpose is that "it returned" is not "it worked".

### 54 — never pipe a gate; read the exit code's VALUE

54. **`cmd | tail` reports TAIL's exit code — a gate that never ran reports success** — two UX-P064 gate runs recorded a clean `0` over runs that never happened. `set -o pipefail` is not on in these shells, and `${PIPESTATUS[0]}` is bash-only (**in zsh it expands to empty**, so the line prints `EXIT:` and the reader supplies the zero). Canonical form: never pipe a gate — `cmd > /tmp/gate.txt 2>&1; echo "EXIT CODE: $?"; tail -20 /tmp/gate.txt`. Gate evidence whose exit code came through a pipe proves only that `tail` is healthy. **AMENDMENT (Alex, 2026-08-14): read the exit code's VALUE, not just whether it is zero — a non-zero exit that isn't `1` usually means the gate NEVER RAN.** Runners reserve `1` for "what you asked me to check failed" and spend other codes on "I could not check": pytest `2` interrupted / `3` internal / `4` usage error, bad path / `5` collected nothing; `127` command not found; `137` SIGKILL (OOM); `143` SIGTERM. **`1` is a result; everything else is a story about the harness.** Treat a non-1 non-zero as a FAILED GATE, not a failing test, and go find why it could not run. (Full entry: gotchas #124.)

---

## CI Test Coverage — the full file-by-file table

*Trimmed from `## CI Test Coverage`. The replacement keeps the rule (every fix adds a guard test for its class) and points at `docs/quality-audit.md`; the historical table is here.*

| Test File | What It Catches | Added |
|-----------|----------------|-------|
| `tests/test_startup.py` | Import errors that crash the web dyno | Original |
| `tests/test_tasks_wiring.py` | Missing/duplicate Celery beat schedule entries | Apr 2026 |
| `tests/test_alembic.py` | Multiple heads, deleted migrations, orphaned revisions | May 7 |
| `.github/workflows/ci.yml` (frontend-build) | ESLint + TypeScript errors blocking Vercel | May 7 |
| `tests/integration/test_route_feed_scoring.py` | Feed scoring, ordering, event/futures data shape with seeded data | May 8 |
| `tests/integration/test_route_events_seeded.py` | Event detail response shape, game-markets sections, related futures | May 8 |
| `tests/integration/test_route_category_pages.py` | Weather, politics, entertainment, economics API response shapes | May 13 |
| `tests/integration/test_route_futures_browse.py` | Futures browse, categories, movers, compare response shapes | May 15 |
| `tests/integration/test_route_market_moves.py` | Market moves endpoint response shape and param validation | May 15 |
| `tests/test_politics_normalization.py` | Politics probability normalization for independent binary markets | May 15 |
| `tests/test_rate_limit.py` | Rate limiting middleware: thresholds, auth exemption, Redis fallback | May 15 |
| `backend/tests/test_*` guardrail suites | Discover scoring/personalization, matching, ingestion/quota, display, auth/preferences, calibration/identity, provider parsers, retention/taxonomy | May 17 |
| `tests/test_feed_discover_event_demotion.py` | Event demotion bypass: league-tier gating, EI thresholds, headline keyword exceptions | May 18 |
| `tests/test_feed_dismiss_propagation.py` | Story-key and group_id dismiss propagation in personalization context | May 18 |
| `tests/test_futures_highlights.py` | Election allowlist, soccer allowlist, non-major election penalty | May 18 |
| `tests/test_cross_source_matching.py` | Cross-source matching: normalization, pairing, delta computation, dedup | May 18 |
| `tests/test_personalization.py` + `tests/test_feed_discover_affinities.py` | Semantic dismiss soft penalty, generic-token guardrails, and semantic token extraction | May 18 |
| `tests/integration/test_route_auth.py` | Auth endpoint contract: Google/Apple sign-in, /me profile, validation | May 18 |
| `tests/integration/test_route_challenges.py` | Daily/friend challenge creation, acceptance, validation | May 18 |
| `tests/integration/test_route_league_futures.py` | League futures sections, sport key routing, market classification | May 18 |
| `tests/integration/test_route_notifications.py` | Device token registration, admin token management, push test | May 18 |
| `tests/integration/test_route_source_intelligence.py` | Source intelligence main + 5 audit endpoints, admin auth | May 18 |
| `tests/integration/test_route_teams.py` | Team detail page shape, 404 handling, championship path | May 18 |
| `tests/integration/test_route_user.py` | Pins, preferences, favorites, sport affinities, onboarding | May 18 |
| `tests/integration/test_route_sports.py` | Sports list, detail, hierarchy, hierarchy-detail, admin auth | May 18 |
| `tests/integration/test_route_weather.py` | All 7 weather endpoints, seeded data shapes, cross-source | May 18 |
| `tests/integration/test_route_economics.py` | Economics themes, Fed/CPI/recession seeded data, by-source | May 18 |
| `tests/integration/test_route_politics.py` | Politics themes, presidential normalization, SCOTUS/policy classification | May 18 |
| `tests/integration/test_route_entertainment.py` | Entertainment themes, empty DB defaults, HTTP methods | May 18 |
| `tests/integration/test_route_feedback.py` | Bug report submission, optional fields, minimal body | May 18 |

