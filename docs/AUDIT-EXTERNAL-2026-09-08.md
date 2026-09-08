# BainLuck: reliability and execution audit

**Alex Bain · September 7, 2026 evening Pacific / September 8 UTC**

**Recommendation:** concentrate the next reliability cycle on three complete outcomes: one correct page per game, fresh and consistent probabilities, and fast loading that survives deployments. Finish the existing work on those outcomes before adding more features or another layer of process.

BainLuck has substantial engineering infrastructure already. The problem is not simply insufficient tests, monitoring, or architecture. Several protections cover one path while another writer, reader, or operational step bypasses them. The result is considerable activity without consistent end-to-end correctness.

## Scope and confidence

- Cloned `alexander-bain/bainluck`, inspected architecture, product and operating documents, and traced targeted ingestion, identity, lifecycle, refresh, caching, deployment, and rendering paths.
- Audited commit **9894d15d7533908c4c8562735a0bf4e03cc9437f**. The public API's `/health` returned `9894d15d`, confirming the backend was serving this commit. The latest CI and deploy jobs succeeded. The frontend's exact deployed SHA was not independently established.
- Inventoried all **1,267 open issues and 58 open pull requests**, deduplicated across 14 API pages. Read the latest 100 issue bodies and additional targeted issues/comments in depth; this is not a claim to have individually adjudicated all 1,267 issues.
- Inspected Discover, Sports, Red Sox search and team-page navigation, and a reported Manchester City event in the live desktop browser. Compared the Red Sox schedule against MLB's public schedule API. Read public BainLuck API responses.
- Executed a focused diagnostic using the actual lifecycle helper and the `auto_create_status` function extracted from the checked-out source. Did not run the entire test suite, mutate production data, change code, create issues, merge PRs, or deploy.
- Native-app findings are based on code/issues, not a hands-on iPhone run. Browser inspection was desktop-width, not a measured mobile-device test. No production SQL access, query plans, or current database resource telemetry were available.

Evidence below is distinguished as **live observation**, **code-confirmed mechanism**, **reported production incident**, or **recommendation**. Historical issue counts are not presented as fresh production measurements.

## 1. What is visibly broken

| Journey | Observed during this audit | Implication |
|---|---|---|
| Search “Red Sox” → team | Team is the first suggestion, which is good. Its page says **MLB PRESEASON**, **13–15**, in September. | Search finds an identity, but the identity/context is wrong. Existing issue #3661 is still reproducible. |
| Red Sox upcoming/recent games | Two Angels entries at the same September 8 start time get G1/G2 labels. September 5 and 6 Orioles results also appear as paired G1/G2 rows. MLB reports one game on each date, `doubleHeader=N`. | Duplicate records are being given the appearance of legitimate doubleheaders. |
| Red Sox championship outlook | Hero/season journey show 5%; division comparison shows 3%; season futures include 6% and 5% championship entries. | Different interpretations, sources, timestamps, or seasons reach the same page without enough distinction. The exact cause of each discrepancy needs a payload comparison. |
| Sports live rail | Cardinals–Giants appears twice: event **15306176**, with score/inning, and **15299649**, with a different spelling and no score. | Duplicate identities reach a main product surface, not merely an obscure database corner. |
| Manchester City–Sunderland | Event **15306788** says “No result reported,” dated September 6 Pacific, with an 8% home probability. Event **15305236** is scheduled September 20 and carries a 0.8966 sportsbook value. | The reported false-LIVE specimen has changed state, but the wrong-date duplicate remains. These are conflicting records, not evidence of meaningful market disagreement. |
| Same Manchester City page | “Championship path” includes NWSL, USL, Ecuadorian and Chinese league championships. | Related-market retrieval is admitting unrelated entities; attractive formatting cannot repair that join. |
| Discover | Several explanatory captions differ by one point from the adjacent displayed probability, e.g. 22% versus 23%. | Generate the caption and number from the same value, timestamp, and rounding function. Small, but particularly avoidable in a product promising one number. |

Sources: [Red Sox page](https://www.bainluck.com/sport/baseball/mlb/team/boston-red-sox), [Sports](https://www.bainluck.com/sports), [Manchester City specimen](https://www.bainluck.com/events/15306788), [official MLB schedule response](https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=111&startDate=2026-09-05&endDate=2026-09-09), [#3661](https://github.com/alexander-bain/bainluck/issues/3661), [#3840](https://github.com/alexander-bain/bainluck/issues/3840).

## 2. Schedule integrity: stop manufacturing certainty

### A. A missing kickoff can become “now,” then become LIVE

**Code-confirmed.** In `_create_event_from_prediction_market`, `market.commence_time` is replaced with `now` if absent or more than 30 days away. `auto_create_commence_time` returns that fallback with no provenance when no ticker is parseable. `auto_create_status` then treats it as live because it is at or before now.

The existing protection recognizes `kalshi_ticker` as a derived time. It does not reject `None` or `polymarket`. The focused source diagnostic returned:

| Time provenance | Treated as reported start? | Status when supplied fallback equals now |
|---|---:|---|
| `None` | Yes | live |
| `polymarket` | Yes | live |
| `kalshi_ticker` | No | scheduled |
| `espn` | Yes | live |

This explains how the code can transform “we do not know the start” into “this game started.” It also explains why a guard checking whether LIVE precedes the stored kickoff misses the error: the stored kickoff is itself wrong.

**Fix:** explicitly distinguish a verified start, a date-only hint, and an unknown start at the writer. A fallback used for sorting must not drive lifecycle. Keep the unverified claim available for resolution, but do not publish it as a started game. Do not globally reject every legacy `None` provenance row; the code explains that many valid historical rows lack this field. Target new unverified writes and repair the identified contaminated cohort separately.

**Acceptance:** a missing, date-only, close-time, or distant market timestamp never creates a false live/finished game; a subsequent authoritative schedule observation updates the same resolved fixture. Test the actual writer-to-serializer path, not just the helper.

Sources: [writer, around lines 4925–4970](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/prediction_market_matching.py#L4925), [start-time guard](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/utils/event_completion.py#L73), [#3840](https://github.com/alexander-bain/bainluck/issues/3840).

### B. Finish identity reconciliation through every consumer

**Existing program, partly implemented.** #2693 already specifies receipts, database invariants, and a golden set. The repository already has `EventProviderAnchor`, namespaced provider keys, a unique ESPN-ID index declaration, and proven-duplicate folding. Recommending a brand-new “canonical event system” would ignore work you have already done.

The remaining problem is the complete path: two providers identify one fixture; all valid markets and histories reach its canonical presentation; search, team, league, Discover and event detail resolve the same identity. Unique IDs per provider cannot by themselves prevent two rows carrying different providers' IDs from representing the same game.

The latest #2693 comments report a real success: six US Open quarter-finals now print one card with prices folded in from the suppressed twin. They also name the remaining populations. Extend that work deliberately. Do not relaunch its solved subproblem, and do not interpret every refused candidate pair as a confirmed duplicate.

**Fix:** resolve provider observations onto canonical fixtures with competition, participants, gender/squad, round/leg/game number, and schedule provenance. A changed start is an update to identity, not a new identity. Use the existing authoritative mapping and reversible read-fold mechanisms where appropriate. Ambiguous name/time matches must remain unresolved rather than silently merge distinct games.

For repairs, preserve price histories and old links; verify that suppressing a duplicate does not remove its only usable prices. A tagged duplicate is not fully fixed while direct links or a secondary surface still serve conflicting data.

**Acceptance:** the Red Sox and Cardinals examples resolve once across every surface; a real doubleheader still has two fixtures; rescheduled soccer games keep identity; repeated names in tennis do not cross gender, tournament, or round; source curves remain attached to the correct participant.

Sources: [#2693 and progress comments](https://github.com/alexander-bain/bainluck/issues/2693), [anchor model](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/models/models.py#L2273), [#3813](https://github.com/alexander-bain/bainluck/issues/3813), [#3810](https://github.com/alexander-bain/bainluck/issues/3810).

### C. Stop explaining away duplicates in the UI

`assignGameNumbers` groups baseball entries by opponent and day, then numbers every group with two or more rows. It does not require provider-confirmed doubleheader metadata. A previous fix limited this behavior to baseball; the same logical error remains within baseball.

**Fix:** render G1/G2 only from authoritative game-number/doubleheader metadata. Fix the upstream duplicates as part of the same ship; removing the label alone leaves the user with two entries.

**Acceptance:** the September 5, 6 and 8 Red Sox examples display one fixture each, while an actual MLB doubleheader retains the correct game numbers.

Source: [assignGameNumbers](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/frontend/lib/teamGames.ts#L117).

### D. Make the schedule provider contract sport-specific

The older StatPal `get_fixtures("soccer")` reads tomorrow and the following day, with a stale comment claiming offset zero is unsupported. Newer code correctly explains that zero is the live board, not a full-day schedule. Therefore “just add offset zero” is an incomplete repair: active-board coverage and schedule coverage have different meanings.

**Fix:** consolidate callers onto the measured adapter contract and combine the current live board with the required schedule/result windows. Monitor the expected active fixtures, not merely HTTP success or a nonempty forward schedule. Preserve the qualified fixture-ID namespace; the repo already documents collisions between StatPal ID spaces.

Sources: [StatPal adapter](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/services/statpal_api.py#L506), [#3800](https://github.com/alexander-bain/bainluck/issues/3800), [#3094](https://github.com/alexander-bain/bainluck/issues/3094).

## 3. Performance: protect the work that keeps reads fast

### A. Frontend changes should not restart long-running backend jobs

**Reported incident plus code-confirmed coupling.** #3665 reports 23 incomplete matcher passes out of 46 starts in an approximately 11.3-hour counter window. A matcher pass uses about 745 seconds of a 780-second budget on a 900-second beat. Releases interrupt it, and late work can starve repeatedly.

The health reporting for incompletes has since improved; the operational problem remains open. Do not spend the next cycle merely re-fixing the health label.

CI deploys Heroku on successful master pushes without a backend-change condition. The audited tip was a frontend-only merge, and its Heroku deploy job succeeded. The ten sampled recent master CI runs all succeeded; most took roughly 10–12 minutes, with two longer runs. This is not an across-the-board broken-CI diagnosis.

**Fix, in order:**

1. Avoid a Heroku release for frontend-only changes, with the path/dependency decision covering shared contracts, backend dependencies and release configuration.
2. Batch compatible backend releases so ordinary cosmetic work does not continually interrupt ingestion. Retain urgent release capability and existing review gates.
3. Break long matcher/refresh jobs into bounded, resumable units. Persist progress so a worker restart cannot send every pass back to the same early rows. Prioritize imminent games but reserve capacity so the remaining population eventually completes.
4. Test a deliberate worker interruption halfway through a batch: no duplicated writes, no lost committed links, and the unprocessed tail runs on resumption.

Longer term, independently deploying workers is worth considering if interruption persists. It is not a prerequisite for the first fix.

Sources: [#3665](https://github.com/alexander-bain/bainluck/issues/3665), [deploy job](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/.github/workflows/ci.yml#L1458), [latest successful CI](https://github.com/alexander-bain/bainluck/actions/runs/34116308840).

### B. Close the database orphan-query recurrence

**Reported production incident, not freshly measured here.** #3776 records multi-day calibration queries pinning PostgreSQL's cleanup horizon. The issue reports a sampled query falling from 7,465 ms to 112 ms after orphan termination and cleanup. Its comment says the operational mitigation was performed but the recurrence fix remains open.

There is already a 1,500-second timeout constant and per-phase/per-unit timeout code. Thus “add a timeout” is too shallow: verify the effective timeout on the actual heavy-query connection, after commits/rollbacks, on every execution path. The presence of a constant does not demonstrate that the server running the troublesome query uses it.

**Fix:** establish finite database-side limits for heavy work, safely below its worker termination window; record connection/run identity; ensure each transaction re-establishes its intended settings; make a killed worker unable to leave a query running for days. Use short, resumable transactions and protect interactive query capacity. An additional queue on the same database does not isolate database I/O or cleanup impact.

**Acceptance:** intentionally interrupt a representative job in staging and show that its database backend exits within the declared bound; interactive latency and cleanup remain healthy. Verify the database's actual version before selecting version-specific timeout options. Do not implement an automatic query-killer based solely on SQL starting with `WITH` or `SELECT`—those strings alone are not a safe proof of harmlessness.

Sources: [#3776 and mitigation comment](https://github.com/alexander-bain/bainluck/issues/3776), [existing timeout](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/precompute_calibration.py#L482), [transaction timeout wiring](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/calibration_main_build.py#L966), [PostgreSQL timeout documentation](https://www.postgresql.org/docs/current/runtime-config-client.html).

### C. Measure the whole loading journey and retain freshness

The homepage is a client page, but it already includes a parse-time boot fetch for eligible first-time anonymous visitors. There are also caches, warmers and bounded feed pagination. “Add caching and skeletons” would be redundant advice.

My public-request sample was:

| Request | Remote elapsed | Relevant observation |
|---|---:|---|
| Health | 7.737 s | Returned audited SHA |
| Discover API | 5.773 s | Cache hit; server reported **5.64 ms**; response 72,079 bytes |
| Red Sox typeahead | 6.072 s | Response 1,977 bytes |
| Two event-detail requests | 5.687 / 4.968 s | Both returned successfully |

These are individual observations from the audit environment, **not user p50/p95 measurements**. Even health was slow here; these timings cannot establish that the application handler spent five seconds computing. They also do not measure hydration, rendering, or phone interactions.

**Fix:** use the existing latency program to compare first-time, returning-anonymous, and signed-in cold opens. Record navigation → useful card → interactive state, alongside API time, cache state, and content age. Your PRD already calls for cold first-load and search p50 ≤1 second; keep that goal and add a tail measure rather than optimizing only warm averages.

For Discover, investigate a server-rendered/shared first useful card or an equivalent bounded initial payload, followed by personalization and deferred charts. Preserve the boot-fetch single-request guarantee. The objective is useful content immediately, not another skeleton.

**Freshness defect confirmed in code:** `_prewarm_feed_shape` omits `oldest_artifact_age_s` when calling the same TTL helper used by the request path. A cached response can outlive the allowed total age of the data used to build it. Fix #3841 with the warmer cadence/coverage work from #3827; shortening TTL in isolation can bring cold builds back.

Sources: [boot-fetch implementation](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/frontend/lib/discover/feedBoot.ts), [warmer TTL call](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/precompute_category_pages.py#L1109), [#3841](https://github.com/alexander-bain/bainluck/issues/3841), [#3827](https://github.com/alexander-bain/bainluck/issues/3827).

## 4. Price freshness: discovery is not maintenance

**Code-confirmed coverage limit, with incident-reported population.** The Polymarket discovery scan is limited to 20 newest-first pages. #3879 reports 56,721 served futures legs older than 24 hours and 37,041 older than a week. Its title and body use slightly different total counts, so I would not quote a precise stale percentage without recapturing the population.

Other refresh jobs cover selected tiers or registered tournaments. They do not guarantee maintenance for everything the site serves. #2637 describes the related problem on the closed-event scan. A provider call succeeding is insufficient if older records are never reached.

**Fix:** separate discovery, price refresh and settlement reconciliation. Use durable cursor-based enumeration for full coverage, plus an addressed refresh of known served-and-stale markets, ordered by urgency. Polymarket now documents `/events/keyset` with `next_cursor` → `after_cursor`; validate the adapter against its actual response shape. Refresh a complete market's outcomes together so a ladder cannot combine fresh and old legs.

Track last successful price observation separately from row-update time and last price change. A repeatedly confirmed unchanged price is fresh; an unrelated metadata update is not a refreshed price. Apply source-age eligibility before blending and preserve the input timestamps in the published result.

**Acceptance:** older active markets and newly closed markets are reached across successive bounded runs; the served Tier 1/2 cohort meets #3879's ≤24-hour ceiling, with much tighter sport/state-specific budgets for live play. Unknown or expired data cannot silently wear a current label.

Existing work to evaluate first: [PR #2669](https://github.com/alexander-bain/bainluck/pull/2669) addresses resolved-status sync by event ID; [PR #3873](https://github.com/alexander-bain/bainluck/pull/3873) addresses tennis ladders. Neither should be assumed to close general population refresh without proof.

Sources: [bounded scan](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/tasks/polymarket.py#L629), [#3879](https://github.com/alexander-bain/bainluck/issues/3879), [#2637](https://github.com/alexander-bain/bainluck/issues/2637), [Polymarket keyset documentation](https://docs.polymarket.com/api-reference/events/list-events-keyset-pagination).

## 5. Make one number actually mean one number

Use the existing server display-contract work to define a single answer for a question, participant and time context. It should carry canonical identity, competition/season, market meaning, participant orientation, pregame/current/final state, probability, observation time and contributing source provenance. Web and native should render it consistently.

This is especially important for related futures. The code's name-pattern builder expands team names into city and individual-word patterns. Those terms can find candidates; they are not sufficient evidence that the result concerns the team or competition. Manchester City's NWSL/USL “path” is the user-visible counterexample.

**Fix:** validate related results against canonical entities and market semantics after retrieval. Do not allow a broad text match to become an affirmative relationship. Bind same-question hero, grid, caption and chart to the same answer; label different seasons or time contexts explicitly. The same applies to pregame versus settlement prices and cumulative probabilities versus bucket densities.

**Acceptance:** a supplied payload produces consistent numbers on all supported surfaces; cumulative ladders are monotone in the correct direction; exclusive outcomes satisfy their declared completeness contract; impossible settled outcomes do not remain actionable. Do not normalize unrelated or nonexclusive markets to 100% just to make a test pass.

Sources: [team-name patterns](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/backend/app/routes/events.py#L9215), [#3667](https://github.com/alexander-bain/bainluck/issues/3667), [#3807](https://github.com/alexander-bain/bainluck/issues/3807), [#3850](https://github.com/alexander-bain/bainluck/issues/3850), [#2911](https://github.com/alexander-bain/bainluck/issues/2911).

## 6. How to make faster progress

### Reduce the active problem count, not ambition

The inventory contains **19 P0s, 358 P1s, 533 P2s, 210 P3s, and 147 issues without a priority label**. There are 105 `matching-symptom` issues, 105 `alert-intake` issues, 106 parked issues, and 45 `needs-user` issues; these categories overlap. All open issues lack GitHub assignees, but ownership does exist in comments and lane conventions—do not confuse absent assignees with absent owners.

With 358 P1s, “P1” cannot choose today's work. Keep the historical board, but operate from a small ranked set of complete ships with an explicit accountable owner, current blocker, existing PR, and next verifiable user outcome. Attach symptom reports to the root work instead of turning each into a new independent queue.

A practical priority score is affected user journeys × frequency × trust damage, divided by remaining effort to deliver the whole fix. This favors wrong games, false lifecycle and stale probabilities over extra instrumentation or isolated wording polish.

### Give one owner responsibility through repair and live verification

Preserve independent review and the single integrator. But a user-visible defect should have one accountable owner across code, review, deployment, data repair, and every affected surface. The owner need not perform every step. They must be able to finish the dependency chain rather than repeatedly file work for another lane.

Differentiate **merged**, **deployed**, **data repaired**, and **user journey verified**. #2693's progress comments illustrate why: a correct folding function still needed the tags applied before its user-visible benefit existed.

### Consolidate operational instructions without erasing decisions

There are 664 tracked files under docs, 148 under docs/rulings, and 1,449 lines in PRODUCT-BRAIN. Scale alone is not a defect, but I found concrete drift:

- The anchor-channel design still opens “DESIGN ONLY,” while the table/model/writer have since shipped.
- CLAUDE.md describes the April matching audit's 100% result, with a staleness caveat, while current matching failures are extensive.
- PRODUCT-BRAIN's “How to use this” points to an ordered local backlog, while other operative text says GitHub is the sole priority source.
- Essential runtime queues are machine-local and absent from a clean clone. The repo itself recognizes this visibility problem.

Maintain a short current operating index: active rules, superseded rules, source-of-truth links, owners, and shipped versus staged capability. Keep the historical rulings intact. Link old designs to current implementation/status. This should replace repeated rediscovery, not launch a documentation-only program.

### Test the missing connections, not just more functions

The repository contains 27,681 statically counted backend `test_*` function definitions—not a collected pytest execution count—and substantial real-Postgres CI. “Write tests” is not specific enough.

Extend the existing flow/schedule sentinels and integration fixtures with a compact replay corpus: Red Sox duplicate, real doubleheader, rescheduled soccer, missing kickoff, tennis round/gender collision, old Polymarket market, final-result transition, and interrupted matcher batch. Replay raw provider observations through ingest → identity → pricing → served payload → rendered result. Include deliberately wrong inputs and verify rejection.

Measure **correctly served canonical fixtures / fixtures expected from the schedule authority**, plus phantom extras, duplicates, freshness, and available expected sources. Do not use only `event_id IS NOT NULL`: #3778 documents 100% attachment while markets sat on self-created ghosts. Also track market-only claims outside authority coverage separately; do not silently erase them from the product or denominator.

### Keep the product goal focused

The current PRD is stronger and more current than older Pulse-only positioning: one trustworthy blended probability, the pregame script, live context, discovery, and fast answers. Keep those differentiators.

For the next cycle, add no new sport/provider/platform surface. Use MLB plus the current marquee tennis and NFL journeys as acceptance fixtures while fixing shared mechanisms for all existing coverage. This is sequencing engineering attention, not abandoning broad coverage or dropping inconvenient markets from calibration.

Use your existing **Kalshi-free fortnight** as the owner outcome, plus a small observed set of target users: can they find the game, understand the number and props, and return tomorrow? They should test comprehension and interest; they should not become the production monitoring team.

Sources: [PRD](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/docs/PRD.md), [PRODUCT-BRAIN](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/docs/PRODUCT-BRAIN.md), [anchor design](https://github.com/alexander-bain/bainluck/blob/9894d15d7533908c4c8562735a0bf4e03cc9437f/docs/event-provider-anchor-channel-1946.md), [#3778](https://github.com/alexander-bain/bainluck/issues/3778).

## 7. Proposed next execution cycle

These are priority and scope recommendations, not changes made to your board or promises of completion dates. Use the existing lanes and issue parents; do not create six competing programs.

| Order | Concrete ship | Existing work to consume | Acceptance before calling it done |
|---|---|---|---|
| 1 | A market without a real kickoff cannot appear as a live/finished fixture | #3840, #2693 | Writer + existing-row repair + all serializers verified; no false time promotion |
| 2 | Frontend changes stop disrupting price/schedule jobs; heavy queries cannot survive indefinitely | #3665, #3776 | Frontend-only release avoids worker restart; interrupted batch resumes; DB timeout demonstrated on real connection |
| 3 | Red Sox and marquee games appear once, with all valid source data | #2693, #3661, #3810; evaluate PR #3856 | Search, Sports, team, detail, chart and old links agree; true doubleheaders preserved |
| 4 | Previously discovered markets keep receiving prices and settlement updates | #3879, #2637; evaluate PR #2669 and #3873 | Full enumeration advances durably; served stale cohort declines; completed markets transition |
| 5 | Cold first useful content is fast without misrepresenting data age | #3827, #3841, latency program | First/returning/signed-in measurements; bounded freshness across route and warmer; no extra duplicate fetch |
| 6 | A team/event page tells one coherent probability story | #2911, #3667, #3807, #3850 | Same-question numbers agree; related markets belong; ladders and pregame/final labels are correct |

Suggested staging: the first two are immediate containment and operational work; then complete the identity and refresh ships before expanding feature scope. Calendar the larger work only after its existing branches, blockers and data-repair scope have been reconciled.

The report's most important management recommendation is this: **judge the next cycle by fewer broken user journeys, not more merged fixes, certifications, or new sentinel findings.** You already wrote versions of that rule into the repo. The opportunity is to make the working queue, ownership boundaries, and release mechanics actually enforce it.
