# CLAUDE.md

Read this file before repo work.
Alex's current session instructions take precedence.

Keep this file at **15,000 bytes or less** (`backend/tests/test_claude_md_size.py`).
The original instructions are preserved unchanged in
[the Day 0 reference](docs/release-loop/claude-before-day0-20261101.md).

## Pillars and ships

**MATCHING · DISCOVER · FORMATTING · TRUTH** are the constitution
(`docs/PRODUCT-BRAIN.md`, "THE FOUR PILLARS") and govern code, architecture and UX.
**Every future queue in this repo serves a named user-visible ship.**
A queue names its PILLAR and its SHIP: what a person will be able to see or do.
Measurements earn a place only when they unblock that ship; park the others.
**Certs, audits, sentinels and probes are never the ship.** Reliability gates remain required.
Architecture work may only ride an already queued user-visible ship.
**Architecture-only programs are forbidden**.

## Product Priorities (ordered; re-ratified with Alex 2026-07-13/14)

1. **Reliability — "the app does what it's supposed to do"** — the six failure classes hunted by the Flow Sentinel + Alex's dogfood loop. Success = sentinel-green nights + Alex's Kalshi-free fortnight. `docs/PRD.md` §2.
2. **Discover feed** — guaranteed-interesting, diversity caps scoped by card type (game events are never capped into an empty tab — #1091's lesson), stale-content-free, graceful end state
3. **Event pages with props as the story** — blended win-prob hero + THE SCRIPT vs THE DIVERGENCE vs WHAT HIT. Success = Alex's pre-game ritual test.
4. **Instant Answers** — search finds any entity, merged, first, faster than Kalshi (`docs/strategy-instant-answers.md`)
5. **Event concepts + hubs** — tournaments/cards/ceremonies as unified slug-URL surfaces (`strategy_universal_matching_and_surfaces.md`)
6. **Multi-platform** — iPhone first; watch = top secondary surface; iPad/Mac parity post-iPhone-bar (P7)

**Two standing rulings that shape all of the above (Alex):** *The blend is the product* — one blended probability per outcome; source divergence is a data bug to fix, not a feature to show (deliberate comparison surfaces only). *Settled means settled* — one system-wide settled language: heroes show winners, cards show results, props show the script graded, charts show the completed journey.

## Product rules

- Refer to markets, futures markets, props and events by their appropriate names.
  Reserve "question" for an actual interrogative sentence.
- **never run LLM calls inside `GET /api/feed`**; enrichment is async, bounded and cached.
  Deterministic explanations are first-class; page-one comprehension must not depend on LLM hooks.
- Personalization is bounded and latency-safe: left-swipe is a soft downrank, never a hard dismissal.
- Equivalent markets across sources produce one blended probability per outcome.
- Calibration uses `COALESCE(calibration_probability, opening_probability)`.
  Settled heroes show winners, cards show results, props show grades, charts show the completed journey.
- Anonymous submission must keep working for bug reports.
- No fresh matching measurement means no accuracy claim. **RED means REAL.**
- Credentials NEVER go in tracked files. Keep secrets in untracked environment files or service
  secrets; gitleaks is the backstop. A leak requires rotation, because history retains it.

## Code Style

- **Python**: type hints, Black, Ruff. **TypeScript**: strict mode, interfaces in `lib/types.ts`. **Swift**: `nonisolated struct` models, `@MainActor` only on async methods.

### Frontend Design System (MANDATORY)

The site is **light mode only**. Use the tokens defined in `globals.css` (`bg-surface-*`, `text-text-*`, `border-surface-border`, `text-accent-*`) — never raw Tailwind dark classes, never a hex.

### Analytics (MANDATORY)

Every frontend page needs 3 GA4 hooks before any conditional return: `usePageTracking`, `useScrollDepth`, `useEngagementTime`.

---

## Development Workflow

One branch and one PR per change. CI is the only integrator.
Nothing reaches master except through a merged PR.
Tier A merges on green. Tier B: claude[bot] at head; Fable ACCEPT if reader-visible/destructive/eval (119-A); author window merges.
Tier C requires Alex's tap.
`live-path` is the two-minute lane for live delivery fixes.
NOW #11852 is the only priority list and status line.
Runner inboxes, YOUR-TURN.md and artifacts/ are retired.
Gates prove something about the commit you tested, not the commit you push.

**Build nothing a platform already provides.** GitHub, Heroku, Vercel, Better Stack, Xcode Cloud and the installed Claude GitHub Action handle approvals, deploys, rollbacks, monitoring, signing and review; no custom webhooks, relays, log pipelines, release locks or promotion systems, and nothing for a release-process need inside `backend/app` or `frontend/app`. If a need seems to require one, post the need on NOW first, naming the platform feature that would cover it.

- Migrations use `alembic revision --autogenerate -m "description"`; Heroku applies them on release.
- Backend suite: `cd backend && python3 -m pytest tests/ -v`.
- Before push: `cd backend && python3 -m pytest tests/test_startup.py -v`.
- Frontend before push: `cd frontend && npm run build` (the **ESLint gate**), then `npm run typecheck` (the **TypeScript gate**; needs `.next/types/**`). See gotcha #10.
- Frontend tests: `cd frontend && npx jest`; one suite: `npx jest --testPathPatterns=DiscoverCard` (plural).
- The Heroku release phase imports `app.main` before Alembic; broken imports stop deployment.
- CI runs backend and frontend gates and serializes Heroku deploys with deploy-job concurrency.

Other test commands and admin URLs are in the Day 0 reference.

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

**every fix adds a guard test for its class**. The suite map is in `docs/quality-audit.md`.

## Reference docs

Product judgment: `docs/PRODUCT-BRAIN.md`, `docs/PRD.md`, `docs/doctrine.md`.
Architecture and incidents: `docs/architecture-reference.md`, `docs/gotchas-reference.md`.
Visual language: `docs/design-system.md`. Priority and status: GitHub Issues.
All other original guidance: `docs/release-loop/claude-before-day0-20261101.md`.
