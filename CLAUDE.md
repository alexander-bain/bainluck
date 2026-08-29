# CLAUDE.md

## PROGRESS, NOT MEASUREMENT

**Every future queue in this repo serves a named user-visible ship.** Not a measurement, not an
audit, not a census, not a cert — those are the *means*. The queue names the thing a user will be
able to see or do that they could not before, and that name is the queue's reason to exist. A queue
that cannot name one does not get run.

A measurement is not progress. It is what you buy progress with, and it is only worth buying when
something is waiting to spend it. *(Why — the measure/file/re-measure/certify trap:
`docs/claude-md-overflow-2026-08-24.md`.)*

So:

- **A queue declares its ship in its header**, in user-visible terms — what a person sees, not what
  a table contains. "The 0-7d Kalshi bucket becomes permanently verifiable" is a means; "settled
  markets stop showing a blank result" is a ship.
- **A measurement earns its place by naming the ship it unblocks.** If it unblocks nothing right
  now, it is *parked*, not dropped: append it to `.claude/handoff/PARKED-MEASUREMENTS.md` and move
  on. Parked is a real state, not a bin.
- **Certs, audits, sentinels and probes are never the ship.** They are how a ship is trusted. They
  inherit the ship of the work they verify and are not queued on their own account.
- **This does not license shipping broken things.** The reliability bar and cert tiering
  (ruling 133) are unchanged. The rule is about what a queue is *for*, not about lowering the gate
  it passes through.

**LANE ROLES (Alex ruling 2026-08-25):** build lanes BUILD — their only permitted measurement is their own gates (tests, deploy checks, rollback verification). All other measurement — censuses, probes, audits, diagnosis, and every cert — belongs to the measurement lane (the non-Claude windows on the mission bus), fed by PARKED-MEASUREMENTS.md and staged only when a named ship needs the answer. Heavy measurement queries never run while an attended fold or apply is in flight. An idle build lane is a signal, not a failure — never fill it with measurement.

The LANE ROLES paragraph is Alex's wording and is the operative text; `docs/rulings/134-build-lanes-build-measurement-is-its-own-lane.md` carries the reasoning and the binds.

**QUEUE LAW (Alex 2026-08-28) — a queue names its PILLAR and its SHIP.** The four pillars —
**MATCHING · DISCOVER · FORMATTING · TRUTH** — are the constitution (`docs/PRODUCT-BRAIN.md`,
"THE FOUR PILLARS") and are supreme over every codebase, architecture and UX decision. Every queue
header carries both: the pillar it serves, and the user-visible ship it delivers. Neither substitutes
for the other — a pillar with no ship is a mission statement, a ship with no pillar is a task — and a
queue that cannot name both does not get run.

**THE RIDER RULE.** Architecture work is permitted ONLY as the substrate of a named user-visible
ship that is *already queued*. It rides that ship; it is never the cargo. **Architecture-only
programs are forbidden**, however good the architecture. *(Canonical example + Alex's verbatim
constraint: `docs/claude-md-overflow-2026-08-24.md`.)*

Everything below is how to do the work. This section is what the work is for.

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Size rule (enforced by the 40k-char tool limit, guarded by `backend/tests/test_claude_md_size.py`):** this file must stay under 40,000 characters or every lane reads it silently truncated, and it keeps ≥4,000 characters of headroom so the next rule can be added without a scramble. Episodic detail, war stories, rationale and full gotcha prose live in the linked reference docs; this file carries only the operating rules. Trimmed twice (2026-08-24 from 72.6k, 2026-08-28 from 39.5k); everything removed is preserved verbatim in `docs/claude-md-overflow-2026-08-24.md`.

## Project Overview

**Bain Luck** is a prediction market discovery platform that translates betting and prediction markets into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130". Sports odds plus economics, politics, tech, culture and weather, via the Discover feed.

**North Star**: The most engaging way to explore what the world thinks will happen.
**Target User**: Casual fans who want probability-first context — not betting advice.
**Live Site**: https://bainluck.com (Discover is the default landing page) | **Sports Feed**: https://bainluck.com/sports

---

## The #1 Technical Challenge: Semantic Matching

The core magic of Bain Luck is **perfect semantic understanding** of every event, market, and source — grouped and matched so the user sees one unified view. Four layers, measured by `backend/scripts/audit_event_matching.py`: L1 event existence, L2 market→event linkage, L3 futures surfacing, L4 market completeness — all 100% at the last full audit (April 24; the `--self-check` feed parser is schema-stale, #193, so the dated column has not been re-measured — full freshness note in the overflow doc). Grid accuracy duty now belongs to the **Grid Sentinel** (`backend/app/tasks/grid_sentinel.py`, daily 07:25 UTC): it classifies every finding REAL vs EXPLAINED (season-window artifact) vs WATCH (blend-hidden source disagreement — never RED), and files deduped issues only for REAL. **RED means REAL.** The **Flow Sentinel** (`tasks/flow_sentinel.py`, nightly 07:10 UTC) regression-guards the user-facing half and auto-files evidence-packed issues.

**Hill-climb playbook**: `docs/hill-climb-guide.md` — measure → fix biggest bucket → re-measure → repeat.
**Philosophy**: Any metric below target for markets that SHOULD match is a bug, not a feature gap. Distinguish "our bug" from "upstream gap".

---

## Linked Reference Docs

| Doc | Purpose | When to update |
|-----|---------|---------------|
| `docs/PRODUCT-BRAIN.md` | The staging JUDGMENT layer: standing rulings + the WHY + lane split. Rulings from 001 on are each their own file | Never append ruling prose to the body. New ruling = new `docs/rulings/NNN-<slug>.md` + ONE index line |
| `docs/rulings/NNN-<slug>.md` | One file per ruling; `docs/rulings/README.md` has the shape + collision protocol | Whenever a ruling is issued. CI asserts index ↔ files both directions |
| `docs/doctrine.md` | The GENERAL clauses lifted out of rulings — the sentence that survives deleting its case (ruling 081) | When a ruling's clause pays out outside its own case |
| `docs/PRD.md` | The product's voice: vision, reliability bar, journeys, principles | When product theses change (Alex rulings) |
| [GitHub Issues](https://github.com/alexander-bain/bainluck/issues) | The ONLY source of priority and status — docs hold judgment and reference, never ordering | Continuously |
| `docs/github-workflow.md` | Issues/Project operating model | When labels, templates, columns, or handoff rules change |
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin, feed-ranking detail | When architecture changes |
| `docs/gotchas-reference.md` | Full gotcha catalog and incident learnings — the canonical text behind the Hot List below | When new gotchas discovered |
| `docs/claude-md-overflow-2026-08-24.md` | Verbatim text trimmed from this file (2026-08-24 and 2026-08-28): long gotcha prose, feed-ranking detail, CI table, freshness notes, rationale paragraphs | Only when trimming this file again; append a dated section, never rewrite an old one |
| `docs/quality-audit.md` | Audit script usage, check catalog, CI guard-suite map | When checks added/removed |
| `docs/hill-climb-guide.md` | Matching accuracy hill-climb playbook | When layers/gotchas change |
| `docs/feature-reference.md` / `docs/completed-features.md` | Feature docs / shipped log | When features ship |
| `docs/design-system.md` | Visual design system: colors, type, motion, voice, components | When tokens or patterns change |
| `docs/entity-page-templates.md` | Tier system for auto-generated entity pages + the chrome-earning grammar (ruling 027) | When tiers or contracts change |
| `DAILY-OPERATIONS.md` (repo root) | Alex's runbook: window launch lines, settings-file cross-root write grants, backup remote, single-writer invariant | When the operating model changes |

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), ~19,000 tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS / iPadOS / macOS / watchOS | SwiftUI shared codebase, 142 Swift files. Xcode 16 file-system-synchronized groups (`objectVersion = 77`): **filesystem presence IS target membership** — there are no Sources build phases to check. Widget target is wired; the watch complication target is not | TestFlight / direct |

**Key External Services:** The Odds API (5M/mo quota — the constrained one, monitor it), Kalshi (key), Polymarket, StatPal, DataGolf, MLB Stats API, ESPN (undocumented), OpenAI GPT-4o-mini, Pexels (200 req/hr), TMDB (client-side, `frontend/lib/tmdb.ts`), Firebase Auth (Google + Apple Sign-In). Monthly costs: overflow doc.

---

## Development Workflow

- **Deployments from GitHub**: `git push origin master` triggers CI; Vercel deploys frontend, Heroku deploys through the serialized CI `deploy` job after tests pass. **Pushing master is not a step you take because you finished the work.** Under Program Lanes the Integrator alone rebases, gates, merges, pushes and verifies master; ruling 017 requires holding `.claude/handoff/LANE-integrator.lock` for the push in **any** lane that writes master. Gates prove something about the commit you tested, not the commit you push.
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v`
- **Single test**: `cd backend && python3 -m pytest tests/<file>.py::<Class>::<test> -v`
- **Integration tests**: `cd backend && python3 -m pytest tests/integration/ -v`
- **Smoke test (MANDATORY before push)**: `cd backend && python3 -m pytest tests/test_startup.py -v` (<1s, catches import errors)
- **Frontend gates (both MANDATORY before push)**: `cd frontend && npm run build` (the **ESLint gate** — it does NOT fail on TS errors), then `npm run typecheck` (the **TypeScript gate**, a real CI deploy gate — run it AFTER build, which it needs for `.next/types/**`). Ratchet semantics: gotcha #10.
- **Frontend tests**: `cd frontend && npx jest` (single: `npx jest --testPathPattern=DiscoverCard`)
- **Procfile validates imports**: release phase runs `python3 -c "from app.main import app"` before Alembic — broken imports never reach the web dyno.
- **CI runs both** and serializes Heroku deploys with deploy-job concurrency.

Key admin URLs: see Quick Reference at the bottom of this file.

---

## Project Structure

`backend/app/` — `main.py` (FastAPI entry), `models/models.py` (30 SQLAlchemy models), `routes/` (API endpoints), `services/` (external API clients + `event_registry.py`), `config/` (`win_prob_sources.py`, `league_configs.py`), `tasks/` (27 Celery modules), `utils/` (pure logic: `sport_keys.py`, `prediction_market_matching.py`, …); plus `backend/alembic/` (migrations) and `backend/tests/` (~19,000 items). `frontend/` — `app/` (Next.js app router, 30+ pages), `components/`, `lib/` (API client, types, utilities). `ios/Bain Luck/` — SwiftUI, all Apple platforms. `docs/` — documentation.

---

## Core Architecture

Full detail for every subsystem: `docs/architecture-reference.md` (+ the overflow doc). The load-bearing facts:

**Event Registry** (`services/event_registry.py`): unified `find_or_create_event()`, 4-step cascade: exact source ID → cross-source ID → structured match → create. The structured match MUST include completed/closed events, and since ruling 048 an id-less claim NEVER absorbs (gotcha #32).

**Probability Aggregation** (`utils/aggregation.py`): `compute_aggregate_probability()` reads `Event.win_probability_sources` JSONB. Weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via Core `select+update`, never ORM attribute assignment (gotcha #4).

**Prediction Market Pipeline**: `poll_kalshi_markets` (2h) / `poll_polymarket_markets` (1h) ingest all non-crypto markets → `match_prediction_markets` (**every 15 min**; beat schedule is the authority) links game markets three-phase with per-market commits (deadlock avoidance, gotcha #13) → `poll_live_prediction_markets` (2 min, realtime queue) updates prices. Link rate: `/api/admin/prediction-markets/link-rate`. Polymarket multi-market events share `FuturesMarket.group_id` (`polymarket:{event.id}`), which powers feed dedup, cross-source matching, calibration grouping, and related markets; `market_metadata->>'polymarket_event_id'` stores the provider event id.

**Source-Agnostic Resilience**: the system works when any single source goes dark (validated March 2026).

**Discover Feed Ranking** (`routes/feed.py`, `utils/feed_market_quality.py`, `utils/feed_reasons.py`) — pipeline shape in the overflow doc. Operating rules that must not regress: **never run LLM calls inside `GET /api/feed`** (enrichment is async, bounded, cached); deterministic explanations are first-class (never rely on LLM hooks for page-one comprehension); personalization is bounded and latency-safe (left-swipe is a soft downrank, never a hard dismissal); Discover event demotion caps non-exceptional events (`event_pct < 0.3`) at score 35 with tier-gated exceptions; election/soccer/geopolitics allowlists and story caps live in `futures_highlights.py` / `feed_market_quality.py`. Audit target: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20` via `python3 scripts/audit_feed_quality.py`. Full ranking constants and penalty tables: architecture reference + overflow doc.

**Search** (`routes/events.py`): `GET /api/events/search` — broad ILIKE matching ranked by query-time Postgres full-text (event/team text weight A, market names B, outcomes C). No stored ts_vector migration; prove improvements on real search traces before adding triggers.

**Cross-Source Market Matching** (`utils/cross_source_matching.py`): `normalize_question()` + `find_cross_source_markets()` pair Kalshi↔Polymarket questions, ranked by probability delta, with a conservative near-match second pass (thresholds and guards: overflow doc). Used by all category pages.

**Themed Dashboard Pages** (politics, entertainment, weather, economics) share one backend pattern — classify, hint, group, render. Full shape: overflow doc.

**iOS Authentication** (`ios/.../Services/AuthManager.swift`): backend-session-token pattern, **NOT** typical Firebase client auth — provider credential → backend verifies → PyJWT session token (HS256, 30-day) → Keychain. Restore/revocation detail: overflow doc.

**Native code organization**: views under `Views/`, shared UI `Components/`, helpers `Utilities/`, services `Services/`, `ObservableObject`s under `ViewModels/`; `@MainActor` on async mutating methods, not class-wide; read-only published state is `private(set)`.

**Calibration Pipeline** (`routes/calibration.py`, `tasks/backfill_winners.py`): public `GET /api/calibration` (1h cache), pre-aggregated buckets across 3 sources with `price_moved` dimension. Curve price is `COALESCE(calibration_probability, opening_probability)` — **a coalesce, not an exclusion** (gotcha #144 / ruling 103 exist because the fallback was invisible). `backfill_winners` (6h) runs ~35 named phases; `backfill_polymarket_history` (6h) fetches CLOB history.

**Rage Shake Bug Reporting**: shake / `Cmd+Shift+F` → `POST /api/feedback/bug-report` → `/admin/bug-reports` with auto-diagnosis. Anonymous submission must keep working (gotcha #29).

**Push Notifications Foundation** (`routes/notifications.py`, `services/firebase_push.py`): device-token registration + admin send-test. Still foundation, not a shipped notification system. Two live caveats (2026-08-24): `device_tokens` has never held an iOS row (#2109, client side — verdict query in `tools/push-verdict/`), and `POST /api/notifications/register` is unauthenticated (#2118 — fix HELD until the device capture proves the current path).

---

## Product Priorities (ordered; re-ratified with Alex 2026-07-13/14)

1. **Reliability — "the app does what it's supposed to do"** — the six failure classes hunted by the Flow Sentinel + Alex's dogfood loop. Success = sentinel-green nights + Alex's Kalshi-free fortnight. `docs/PRD.md` §2.
2. **Discover feed** — guaranteed-interesting, diversity caps scoped by card type (game events are never capped into an empty tab — #1091's lesson), stale-content-free, graceful end state
3. **Event pages with props as the story** — blended win-prob hero + THE SCRIPT vs THE DIVERGENCE vs WHAT HIT. Success = Alex's pre-game ritual test.
4. **Instant Answers** — search finds any entity, merged, first, faster than Kalshi (`docs/strategy-instant-answers.md`)
5. **Event concepts + hubs** — tournaments/cards/ceremonies as unified slug-URL surfaces (`strategy_universal_matching_and_surfaces.md`)
6. **Multi-platform** — iPhone first; watch = top secondary surface; iPad/Mac parity post-iPhone-bar (P7)

**Two standing rulings that shape all of the above (Alex):** *The blend is the product* — one number per question; source divergence is a data bug to fix, not a feature to show (deliberate comparison surfaces only). *Settled means settled* — one system-wide settled language: heroes show winners, cards show results, props show the script graded, charts show the completed journey.

## Agent Execution Lanes (read before doing ANY repo work)

There is a queue-based execution system in `.claude/handoff/` (protocol: `.claude/handoff/README.md`). Before starting work in ANY session:

1. Check `.claude/handoff/QUEUE.md`. `status: approved` → that queue IS the next work, via the /triage handoff mode. `status: running` → another session owns the lane: do NOT do repo work that could collide.
2. Check `.claude/handoff/SEQUENCE.md` for priority order. Sequence items get staged as queues with briefs, gates, and live-proof requirements — don't execute them ad-hoc. Off-lane ships must be moved to SEQUENCE.md's Consumed section with the same session-end evidence.
3. Whoever ships, updates: the board and SEQUENCE.md must not drift.

A queue-file `status:` line describes execution ("done" = finished running), NEVER a verdict — verdicts live in reports and `CODEX-CERT-LOG.md`.

**Anything that needs Alex — a decision, an attended command, an eyeball — goes into `~/bainluck/YOUR-TURN.md` with exact steps; burying an Alex-ask in a report is a process bug.**

### Non-Claude window mission bus (added 2026-08-24)

Lane4 (codex) and the independent cert window take missions from `.claude/handoff/CODEX-QUEUE.md` and `.claude/handoff/CERT-QUEUE.md` — Fable/triage stage them by writing those files; the windows poll, execute, and append to `CODEX-REPORT.md` (+ a row in `CODEX-CERT-LOG.md` for certs). Two standing rules: the fix's author never runs its cert, and the cert window never audits its own prior cert subjects.

## GitHub Issues + Project Workflow

GitHub Issues is the single source of truth for priority, status, rationale, and workstream context; the Project board is status/ownership. Docs hold judgment and reference, never ordering.

- Rough ideas → a GitHub issue (`type:idea`), not a doc. Scoped work → real issues with outcome, scope, acceptance criteria, verification. The issue body is the record.
- Label with `area:*`, `type:*`, `priority:*` when useful, and routing labels (`needs-agent`, `needs-user`, `blocked`, `alert-intake`).
- Issue `created` date is the promotion date; preserve original source dates when porting from the retired backlog snapshot.
- Treat Project `In Progress` + the `in-progress` label as a collision-avoidance lock: run `python3 scripts/claim_issue.py ISSUE_NUMBER "In Progress" --owner "<context>"` before editing files; check for overlapping files first.
- Canonical labels/columns: `docs/github-workflow.md`. "Next thing to work on" = open `needs-agent` issues, `priority:p0`/`p1` first.

---

## Quota Guard System

The Odds API quota (5M/month) is the most constrained resource. Circuit breaker in `tasks/redis_state.py`: >50K remaining = Normal; 20K-50K = LIVE_ONLY; <20K = FULL_STOP (priority sports only). Live-poll and discovery cadences are tiered by sport — `SPORT_POLLING_TIERS` is the authority, never a number quoted here (per-tier values: overflow doc).

---

## Code Style

- **Python**: type hints, Black, Ruff. **TypeScript**: strict mode, interfaces in `lib/types.ts`. **Swift**: `nonisolated struct` models, `@MainActor` only on async methods.

### Frontend Design System (MANDATORY)

The site is **light mode only**. Use the tokens defined in `globals.css` (`bg-surface-*`, `text-text-*`, `border-surface-border`, `text-accent-*`) — never raw Tailwind dark classes, never a hex.

### Analytics (MANDATORY)

Every frontend page needs 3 GA4 hooks before any conditional return: `usePageTracking`, `useScrollDepth`, `useEngagementTime`.

---

## Database Schema (Key Tables)

`events` (games, scores, EI, `win_probability_sources` JSONB) · `odds_snapshots` (per bookmaker, write-time dedup) · `win_prob_snapshots` · `futures_markets` (championship/award/prop) · `futures_outcomes` · `teams` · `team_identity_mapping` · `user_predictions` · `user_seen_markets` · `users` · `settlement_captures` / `event_provider_anchors` (settlement-truth capture + provider id anchor channel, #1946). Per-table notes: overflow doc; authority is `backend/app/models/models.py`.

**Key columns**: `Event.win_probability_sources` (JSONB), `FuturesMarket.market_tier` (1-5), `.event_id` (nullable FK), `.llm_sport_category`, `.group_id`, `.image_url`, `.hook_description`.

---

## Sport Key Architecture

`utils/sport_keys.py` is the **single source of truth** for sport key translation maps (`SPORT_LEAGUE_MAP`, `KALSHI_TICKER_TO_SPORT_KEY`, `KALSHI_FUTURES_TICKER_TO_SPORT_KEY`, `SPORT_PREFIX_TO_LLM_CATEGORY`). It imports nothing and must stay that way (zero circular-import risk).

---

## Gotchas Hot List

Full catalog with war stories: `docs/gotchas-reference.md`. **These numbers are Hot List positions, NOT catalog ids** — the two spaces are independent and they collide (worked example: overflow doc). Cite the catalog only via an explicit id written into the entry text (#124, #144, #154). This list is rules only — if you need the incident, read the reference.

1. **Alembic revision IDs ≤32 chars**; Alembic uses psycopg2, not asyncpg.
2. **Admin endpoints require mounting** in both `main.py` and `routes/__init__.py`; admin writes need `_check_admin_secret`.
3. **`sport_keys.py` imports nothing** — must stay circular-import safe.
4. **JSONB ORM assignment can silently fail** — use Core `update()` for JSONB writes.
5. **Don't mix ORM assignment with Core SQL** in one session unless you understand flush ordering; prefer Core for task-code writes.
6. **Async rollback expires ORM objects** (`expire_on_commit=False` does not prevent it) — copy rows to scalars before commit/rollback-per-item loops; module-global caches must hold plain data, never live ORM rows (#2107).
7. **Python 3.12+ shadowing imports → `UnboundLocalError`.**
8. **Never delete a migration that has run on Heroku.**
9. **GitHub Actions can't use `secrets.*` in step-level `if`** — check inside the `run` block.
10. **`npm run build` is the ESLint gate, NOT a TS gate; `npm run typecheck` is the TS gate and a real CI deploy gate** — a fail-on-new ratchet vs `frontend/typecheck-baseline.json`: one error MORE than baseline fails, one FEWER also fails (fix → `npm run typecheck:baseline`). Run typecheck AFTER build (needs `.next/types/**`).
11. **The Odds API bills per `events × market_types × regions`**, not per request.
12. **Beat schedule test has an allowlist** — update `tests/test_tasks_wiring.py` when adding scheduled tasks.
13. **Phase 2 matching commits per market** (deadlock avoidance); after rollback boundaries, drop live ORM objects.
14. **Kalshi `commence_time` is often close time, not start** — use ticker-derived dates for matching.
15. **Never time-window already-linked markets** — if `event_id` is set, trust it.
16. **Kalshi ticker abbreviations need explicit mapping** — prefer ticker-derived names.
17. **Kalshi threshold outcomes are OVER probabilities** unless explicitly "Under"/"No".
18. **Polymarket game events are nested sub-markets** — decompose by `condition_id`.
19. **Polymarket midpoint can be stale in blowouts** — wide spread → `lastTradePrice`; no trade and no bid → skip.
20. **Polymarket `group_id` API scan is expensive** — short-circuit when no null rows.
21. **Calibration resolution data is fragile** — never bulk-reset `is_winner` without an immediate re-resolve source.
22. **Completed-event times are not game-end times** — chart domains use the last real snapshot.
23. **Independent binary markets need display normalization** — candidate binaries can sum well over 100%.
24. **Demotion exceptions must be tier-gated** — generic "upset"/"comeback" counts only for major leagues.
25. **Dismiss propagation has blast radius** — story keys suppress for 14 days; semantic dismiss ignores generic tokens.
26. **iOS models: `Decodable`, `nonisolated`, `Double` probabilities**; avoid class-wide `@MainActor`.
27. **iPad Stage Manager can return a background scene** — filter for foreground-active key window.
28. **Extracted Swift files need their own imports**; remove duplicated definitions.
29. **Bug reports keep anonymous submission working** while optional auth captures user identity.
30. **Codex may reject literal `git push`** — use `git -c push.default=simple push origin master`.
31. **Never CREATE INDEX CONCURRENTLY in Alembic** — Heroku release timeout ≈5 min; big indexes go via psql (May 22 outage).
32. **Registry structured match includes completed/closed AND an id-less claim NEVER absorbs — it creates** (ruling 048). Absorption needs an id-anchored correspondence: a shared provider id on the candidate, or the claim's id dereferencing via its own provider's schedule. Neither ⇒ CREATE with provenance; id-keyed reconciliation drains the duplicate. Never restore name-and-time absorption. **Amendment 2026-08-20:** the drain is structurally unreachable for 99.6% of rows until `event_provider_anchors` ships — report those as `NO_ANCHOR_CHANNEL`, never `AWAITING_ANCHOR`; Alex ruled BUILD THE CHANNEL, loosening absorption REJECTED. Full text: ruling 048 + amendment, `docs/event-provider-anchor-channel-1946.md`.
33. **Kalshi settled markets stay `status='open'` in DB** — polling only sees open markets; the settled-events backfill Phase 1 fixes unconditionally.
34. **Never share one counter between status updates and data backfill** across a series loop — early series starve later ones.
35. **Kalshi EVENT data is permanent; MARKET data purges at ≥74/<86 days (measured)** — `scripts/probe_kalshi_retention.py` re-measures; use the constants in `app/utils/kalshi_retention.py` (incl. `CAPTURE_PLANNING_AGE_DAYS = 66`), never a prose day count.
36. **Never catch-all in API clients returning Optional** — `None` for "doesn't exist" may only catch 404; 429 must re-raise.
37. **`box_score_data` is a wrapper dict** — player stats live under the `"players"` key.
38. **`json.loads` holds the GIL for the entire C-level parse** — `asyncio.to_thread` does NOT free the loop. Big decodes: orjson (with fallback), small pages, resumable cursor.
39. **A sync Redis client with no socket timeout can freeze an async task** — always route through `get_redis_client()` (bounded 5s by default; CI-guarded).
40. **Admin `db-query` serializes JSONB as Python repr** — parsers need an `ast.literal_eval` fallback.
41. **Bulk backfills: newest-first starves the old tail; oldest-first over an EXPIRING population without a floor processes the dead first.** A sweep over an expiring population needs BOTH bounds: oldest-first within a floor. Ask what the ordering starts on.
42. **One bad item must never wipe a scoring pass** — per-item try/except in every feed/scoring loop; guard tests assert healthy siblings survive.
43. **Scope diversity caps by card type** — guard tests assert BOTH directions: flood capped AND adjacent surface populated.
44. **Test anchors must not branch on the clock** — offset FIRST, then truncate; if your anchor contains an `if`, it isn't fixed. Prove with `backend/scripts/clock_sweep.py` (12 faked clocks).
45. **`LIKE '%:x'` inside `text()` parses as a bind param** — escape/parameterize; never catch-all around scheduled work without alerting.
46. **`completed_at >= commence_time` is an invariant** — violation means cross-event data merge; any recurrence is a matching-layer P1.
47. **Check `git log origin/master..HEAD` BEFORE committing in a shared tree** — a sibling's fresh commit rides your push.
48. **Non-detached `heroku run` silently fails in the sandbox** — use `heroku run:detached` and verify side effects ~60s later; never trust the empty stdout.
49. **Sentry issue `count` is LIFETIME** — read the 24h stats buckets before triaging by volume.
50. **Headless `xcodebuild` fails on `#Preview` macro sandboxing** — add `OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'`; do NOT nuke the SPM cache.
51. **Every destructive AND write-shaped git verb takes `-C` — and `-C` pins the DIRECTORY, not the BRANCH.** `~/bainluck` is always on `master`; branch work happens only in per-queue worktrees; master-writes only in the Integrator's detached worktree. Before any commit/merge/reset in a shared tree: `git -C <path> rev-parse --abbrev-ref HEAD`. Full history (three amendments): gotchas reference + ruling 056.
52. **No orphan WIP in the shared master tree** — commit to a named branch or stash-with-message in-session; Integrator rescues >24h dirt to `rescue/<date>` at Phase 0. Never reconstruct lost work by archaeology — re-do from intent or rule it unneeded. **See also gotcha #154:** a strip/rebase is not complete until the stripped commits are on a pushed ref or explicitly ruled unneeded.
53. **An empty 200 is not an absence — it is a response shape.** When an API returns the same body for "never existed" and "nothing to report", disambiguate with a second signal (existence lookup, measured retention bound, sentinel) before writing any claim — and make the zero-yield case loud (`app/utils/task_verdict.py`: "it returned" is not "it worked").
54. **Never pipe a gate** — `cmd > /tmp/gate.txt 2>&1; echo "EXIT CODE: $?"; tail -20 /tmp/gate.txt`. And read the exit code's VALUE: **`1` is a result; everything else is a story about the harness** (pytest 2/3/4/5, 127, 137 SIGKILL, 143 SIGTERM = the gate never ran). Full entry: gotcha #124.

---

## CI Test Coverage

CI guard suites cover startup imports, beat wiring, Alembic heads/orphans, the frontend ESLint+typecheck gates, route contracts for every major surface, feed scoring and personalization, matching, and the ruling-ledger/gotcha-numbering integrity gates. The rule that matters: **every fix adds a guard test for its class** (see Quality Audit below). The canonical file-by-file table lives in `docs/quality-audit.md` (moved from here 2026-08-24; historical copy in the overflow doc).

---

## Session Startup: Health Check

Run `/health` at the start of every session. Full definition: `.claude/commands/health.md`.

**Thresholds for immediate action:** Sentry issue >100 events in 24h → triage now · background queue >50 → purge + investigate · endpoint latency >2s → investigate (especially `/api/feed`) · `is_winner` coverage <100% on any source → fix (any gap is a bug) · grid health <100% → investigate.

**Available tools:** Heroku CLI, Sentry API (`$SENTRY_AUTH_TOKEN`), GitHub CLI. All authenticated.

### Credential handling — STANDING RULE (Alex ruling 2026-08-04)

Credentials NEVER go in tracked files — not CLAUDE.md, docs, code, tests, or committed build artifacts (keep `.next*` gitignored). Secrets live only in untracked `~/.claude/.env`, Heroku config, or Actions secrets. **A session holding a real secret must not write it anywhere tracked — file a `needs-user` issue naming the env var only.** gitleaks is the backstop; a finding means ROTATE (history retains it forever), never just delete the line.

**Production API access:** the sandbox may block direct `curl` to `api.bainluck.com`. Workaround: `source ~/.claude/.env` (loads `BAINLUCK_API`, `ADMIN_TOKEN`) in the SAME command as the curl:
```bash
source ~/.claude/.env && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API/api/admin/audit-pass2-guess" | python3 -m json.tool
```
If `~/.claude/.env` doesn't exist, ask Alex to create it — the two `echo` lines are in the overflow doc.

---

## Quality Audit (mandatory practice)

When fixing ANY data quality, matching, or display issue: (1) audit BEFORE: `python3 scripts/audit_matching_quality.py --skip-llm --save`; (2) fix; (3) add a check that catches this class; (4) audit AFTER with `--compare --save`.

---

## Parallel Work Protocol

**Green** — iOS, docs, new test files, new utility files. **Yellow** — different routes, different tasks. **Red** — shared models, migrations, same route/task file. **Never parallelize**: two Alembic migrations, two sessions on one route file, two sessions on models.py.

---

## Quick Reference

**Surfaces** (https://bainluck.com): `/` Discover (default, also `/discover`) · `/sports` · `/discover/stats` · `/admin` · `/weather` · `/politics` · `/entertainment` · `/economics` · `/calibration` · `/privacy`.

**Public APIs** (https://api.bainluck.com, docs at `/docs`): `GET /api/calibration` (1h cache) · `/api/weather/*` · `/api/politics` · `/api/entertainment` · `/api/leagues/{sport_key}`.

**Admin APIs** (Bearer `$ADMIN_TOKEN`): `/api/admin/audit/all` (grid health) · `/api/admin/prediction-markets/link-rate` · `/api/admin/hook-coverage` · `/api/admin/backfill-winners/status` · `POST /api/admin/db-query` (read-only SQL, body `{"sql":"...","limit":500}`).

**Priority + status, the only source:** https://github.com/alexander-bain/bainluck/issues. Judgment, gotchas and architecture: the Linked Reference Docs table above.

| db-query rule | Detail |
|------|-------|
| **Query plan** | same endpoint, `{"sql":"SELECT ...","explain":true}` → `EXPLAIN (FORMAT JSON)`; supply a plain SELECT (the server composes the EXPLAIN). Plan-only does not execute. `"analyze":true` DOES execute (SELECT-only, no leading `WITH`, pure-function allowlist in `app/utils/sql_read_guard.py`, unlisted names refused BY NAME). `"timeout_ms"` 500ms–25s, default 10s |
| **db-query refuses operational functions** | on BOTH the row path and `analyze`: `pg_cancel_backend`, `pg_terminate_backend`, advisory locks, `nextval`/`setval`, `pg_sleep`, `dblink`, `pg_read_file`. `SET TRANSACTION READ ONLY` does not make these safe (#1641). Errors return `{reason, correlation_id}` |
| **Production query timings** | `pg_stat_statements` installed. Caveats (measured): near its 5,000-entry cap so ad-hoc probes get evicted, and errored statements are never recorded — a timing-out query is invisible |
