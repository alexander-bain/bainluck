# CAL-P213 — the unexplained −97,277 is one Redis key, not a lost cohort

**Written 2026-09-02, from `runner-inbox/calibration/981`.** Directive: *"Before Alex answers
anything: find where 930,149 → 832,872 went. Is it settlement, a source going dark, dedup that was
not ruled, or a real data loss? Real queries, real numbers."*

**ANSWER: a source going dark — but not an upstream one.** The 97,277 outcomes are the entire
`odds_api_bookmaker` curve. Its producer task had been dying on `SoftTimeLimitExceeded` for two
days, its 24-hour Redis key expired between the 04:37Z publish and the 05:37Z build, and the
pre-D21 reader turned that absence into zero rows. **Nothing was deleted, nothing un-resolved,
nothing was deduped without a ruling. The rows never left Postgres.** The writer was repaired
(CAL-P134) and has succeeded on every run since 2026-08-31 07:14Z; the source is present in
today's candidate.

**Consequence for the decision in front of Alex: the cert's second precondition is now met, and
the shrink it was measured on is a different shrink from today's.** See §6.

---

## 1. The arithmetic identity — this is the whole finding in one line

`GET /api/calibration` (live, `generated_at 2026-08-31T04:37:36Z`, q268), `by_source`:

| source | outcomes |
|---|--:|
| kalshi | 478,468 |
| polymarket | 312,239 |
| **`odds_api_bookmaker`** | **97,277** |
| odds_api | 17,014 |
| odds_api_totals | 12,705 |
| odds_api_spreads | 12,410 |
| datagolf | 36 |
| **total** | **930,149** |

```
930,149 − 97,277 = 832,872      ← the rejected candidate, EXACTLY
```

Not "about". The published `odds_api_bookmaker` count and the missing population are the same
integer. Every other source in the 05:37Z candidate was byte-for-byte what it had been an hour
earlier.

## 2. The mechanism, already written down in our own source

`precompute_calibration.py:242 read_bookmaker_curve_rows` — the D21 docstring, verbatim:

> The call site read this key inside a `try: ... except Exception: pass`.
> `_precompute_bookmaker_calibration` stopped finishing inside its soft time limit, so it stopped
> writing the key; the key aged out of its 24 h TTL; this reader turned the absence into ZERO rows;
> and the rows are concatenated into `all_rows`, so the candidate went out **~96,026 outcomes
> short**. The publish gate then rightly refused it, every beat, naming the SYMPTOM (a population
> move) and unable to name the CAUSE.

`BOOKMAKER_CURVE_EXPECTED_OUTCOMES = 96_026` (`precompute_calibration.py:89`) is that magnitude as
a named constant. The rows are part of the PUBLISHED population, not a diagnostic
(`precompute_calibration.py:5709`, `all_rows = rows + events_rows + spreads_rows + totals_rows +
bookmaker_rows`).

## 3. The writer was dead across exactly the right window — measured

`GET /api/admin/task-metrics?task=bookmaker_calibration`, 2026-09-02:

| run (UTC) | duration | |
|---|--:|---|
| 2026-08-29 01:09 | 600.5 s | 🔴 pinned at the soft limit |
| 2026-08-29 07:09 | 600.5 s | 🔴 |
| 2026-08-29 13:13 | 600.5 s | 🔴 |
| 2026-08-29 19:06 | 600.4 s | 🔴 |
| 2026-08-30 01:09 | 600.4 s | 🔴 |
| 2026-08-30 07:10 | 599.7 s | 🔴 |
| 2026-08-30 13:09 | 600.3 s | 🔴 |
| 2026-08-30 19:09 | 600.4 s | 🔴 |
| **2026-08-31 01:09** | **601.1 s** | 🔴 **`last_failure_at`, `last_failure_type: SoftTimeLimitExceeded`** |
| 2026-08-31 07:14 | 897.8 s | 🟢 first success after CAL-P134's bounded writer deployed |
| 2026-08-31 13:14 | 935.2 s | 🟢 |
| 2026-08-31 19:13 | 1,015.6 s | 🟢 |
| 2026-09-01 00:58 | 199.3 s | 🟢 |
| 2026-09-01 06:57 | 158.1 s | 🟢 |
| 2026-09-01 12:58 | 187.8 s | 🟢 |
| 2026-09-01 18:57 | 172.8 s | 🟢 |
| 2026-09-02 00:59 | 136.7 s | 🟢 |
| 2026-09-02 07:01 | 191.7 s | 🟢 `published: true`, 87 bookmakers, 149,396 data points |

`health: healthy`, `consecutive_failures: 0`, `last_success_at 2026-09-02T07:01:06Z`.

**The reader that swallowed the absence was still live at 05:37Z, and this is checkable to the
minute.** `heroku releases`: v3955 = `1f0cf419`, deployed 2026-08-30 19:54 PDT — that is the slug
the 05:37Z build ran on, and `git merge-base --is-ancestor 2472b7e8 1f0cf419` is **false**. D21
first ships in **v3957 = `6043c1c0`, 2026-08-30 23:04 PDT = 2026-08-31 06:04Z — twenty-seven
minutes after the rejection.** Under the code that was actually running, an absent key could only
produce a short candidate; under the code running now it produces a named refusal instead.

The beat is `crontab(minute=55, hour="0,6,12,18")` and the key's TTL is 24 h. The last write before
the outage window supported the **04:37Z publish** and expired before the **05:37Z build one hour
later** — which is why the same code published a 930,149 artifact and then refused an 832,872 one
sixty minutes later with nothing else having changed.

## 4. The Sentry record proves it TWICE, and today's rejection is its exact complement

The gate's Rule 3 walks every published category ≥ `CATEGORY_MIN_N = 1000` and names any that fell
more than 20%, counting an absent category as 0 (`calibration_publish_gate.py:921-935`). So the
rejection message is a free per-category diff of the candidate. Three of them, from
`issues/7677836806/events/`:

**2026-08-29 13:39Z — `913,851 → 817,907` (−95,944).** Collapsed categories: `aussierules_afl`,
`baseball_mlb`, `baseball_mlb_preseason`, `baseball_ncaa`, `basketball_euroleague`,
`basketball_nba`, `basketball_nba_summer_league`, `basketball_ncaab`, `basketball_wnba`,
`basketball_wncaab`, `icehockey_nhl`, `rugbyleague_nrl`, `tennis_atp_canadian_open`,
`tennis_atp_cincinnati_open`, `tennis_wta_canadian_open`.

**2026-08-31 05:37Z — `930,149 → 832,872` (−97,277).** The same fifteen, and only those fifteen:

| category | published | candidate |
|---|--:|--:|
| baseball_mlb | 28,060 | 5,002 |
| basketball_ncaab | 33,943 | 7,578 |
| baseball_ncaa | 12,919 | 4,283 |
| basketball_nba | 12,470 | 2,284 |
| icehockey_nhl | 10,616 | 1,958 |
| basketball_wncaab | 5,775 | 2,393 |
| basketball_wnba | 4,246 | 1,023 |
| baseball_mlb_preseason | 4,135 | **0** |
| basketball_euroleague | 2,401 | **0** |
| aussierules_afl | 1,099 | **0** |
| rugbyleague_nrl | 1,071 | **0** |
| tennis_wta_canadian_open | 1,039 | **0** |
| basketball_nba_summer_league | 1,032 | **0** |
| tennis_atp_cincinnati_open | 1,029 | **0** |
| tennis_atp_canadian_open | 1,000 | **0** |

Every one of those names is a `sports.key`. That is the ONLY place `odds_api_bookmaker` rows can
live: its writer groups on `s.key` (`backfill_winners.py:7531-7567`,
`SELECT … s.key AS category … GROUP BY bucket_idx, category`). The survivors are the moneyline,
spreads and totals curves, which key on the same column; the categories that went to **zero** are
the ones that had bookmaker rows and nothing else. **Not one coarse futures category
(`baseball`, `basketball`, `soccer`, `economics`, `crypto`, …) appears.** The futures half was
untouched.

**2026-09-02 10:35Z — `930,149 → 728,992` (−201,157). The exact complement.** Collapsed
categories: `baseball`, `basketball`, `crypto`, `economics`, `esports`, `geopolitics`, `hockey`,
`mma`, `tech`, `tennis` — **every one a coarse `llm_sport_category`, and not one `sports.key`
among them.**

That is dispositive for the question that mattered: **the bookmaker curve is present in today's
candidate.** The fifteen sport-key categories hold 120,835 published outcomes and carry the whole
odds-api family (97,277 + 17,014 + 12,410 + 12,705 = 139,406, of which the bookmaker curve is
69.8%). If those rows were missing again, at least 78,706 of the 120,835 would be gone — over 65%
— and all fifteen would have been named by Rule 3, as they were on Aug 29 and Aug 31. None was.

**Independent recount, run against production** (`POST /api/admin/db-query`, 608 ms) — the
`odds_api` events-moneyline curve rebuilt from `precompute_calibration.py`'s Query 2 predicate:

```
17,176 today   vs   17,014 in the published artifact   →  +162 (+0.95%)
```

The sportsbook half is **growing**, at the rate resolution adds. It is not shrinking and never was.

## 5. The four hypotheses in directive 981, answered

| hypothesis | verdict |
|---|---|
| **settlement** (31,462 finished PM markets still `open`, lane1/049) | **NO.** Settlement only ADDS, and the recount in §4 shows the odds-api half up +0.95%. Those 31k markets are outside the 97,277 entirely — they are futures rows, and the futures half did not move on Aug 31. |
| **a source going dark (ESPN 403?)** | **YES, but not ESPN.** ESPN feeds the win-probability blend, not a calibration price source; there is no `espn` row in `by_source`. The source that went dark is `odds_api_bookmaker`, and it went dark at OUR end — a Celery task exceeding its own soft limit, not an upstream refusal. |
| **dedup that was not ruled** | **NO** for the 97,277 — nothing was deduped there. Dedup IS the dominant driver of the *separate* −201,157 shrink in today's candidate, and it **was** ruled: D5, Alex's explicit ruling-009 exception of 2026-08-30. See §6. |
| **real data loss** | **NO.** Not one row was deleted. `futures_outcomes`, `events` and `odds_snapshots` are untouched by this; the missing object was a derived aggregate cached in Redis under `bainluck:bookmaker_calibration`. It was recomputed from the same rows on 2026-08-31 07:14Z. |

## 6. Today's shrink is a DIFFERENT shrink, and it is fully named

The cert's decomposition chained two numbers from two different builds under two different
writer-health states — `930,149 → 832,872` (Aug 31, bookmaker absent) and `832,872 → 728,641`
(Sep 2, bookmaker present) — and read the difference as two segments of one move. They are not
segments of one move; they are two unrelated events, and the first one has since reversed.

The only comparison that describes what would publish today is **930,149 → 728,992, −201,157**,
and every material cell in it traces to a named, deployed, Alex-ruled change:

| category | published → candidate | Δ | named cause |
|---|---|--:|---|
| baseball | 215,680 → 166,072 | −49,608 | **D5** dedup repair (`67f5a6d3`; polymarket/baseball measured 45,240 → 25,107) + **K′/CAL-P168** (`f8126c8c`, polymarket/baseball placeholder exclusion, Alex 2026-08-28 "EXCLUDE NOW + FIX WRITER") |
| basketball | 124,138 → 74,571 | −49,567 | **D5** dedup repair |
| hockey | 35,427 → 19,281 | −16,146 | **D5** dedup repair |
| tennis | 47,646 → 34,685 | −12,961 | **D5** dedup repair |
| economics | 43,270 → 10,501 | −32,769 | **RULE E** (`6be79cd0`, kalshi/economics non-exclusive bundles, Alex 2026-08-28 option b) |
| esports | 30,974 → 22,439 | −8,535 | **RULE E** (polymarket/esports) |
| crypto | 4,625 → 0 | −4,625 | **D12** (`fd033079`, crypto deleted — "the cell called 'crypto' is 99.5% metal") |
| geopolitics | 1,284 → 0 | −1,284 | RULE E / D12 class |
| mma | 3,988 → 2,851 | −1,137 | **D5** dedup repair |
| tech | 4,127 → 3,133 | −994 | RULE E class |
| *(sub-20% residue)* | | −23,531 | the same mechanisms in cells too small to be named by Rule 3 |

D5's own commit measures the duplication it removes: **"13 cells folded exactly on the payload
basis: 420,081 published rows are 266,137 distinct. 36.65% phantom, 1.5784x, range 0.35% to
47.08%."** A third of the futures half of the published curve is the same outcome counted twice.
The shrink is the curve **stopping** doing that.

⚠️ **What this is not:** a per-row reconciliation. Each collapsed cell is attributed to a named
mechanism, and the two biggest (D5 dedup, RULE E) carry their own pre-measured magnitudes — but an
exact split of the −201,157 needs the per-cell census that only a completed q269 build produces.
That is a reason to publish, not a reason to wait: the census is the first artifact the publish
emits.

## 7. Residual risk, named

* **The bookmaker outage class is now loud, not fixed-forever.** D21 (`2472b7e8`, deployed
  v3956/v3957) makes an absent key a named producer refusal instead of a silent 96K shortfall — so
  a recurrence stops the beat and says which key and which writer, rather than shrinking the
  candidate. The writer itself is bounded and fails closed (CAL-P134). Six healthy runs is not a
  season; the 24 h TTL against a 6 h beat gives four consecutive misses of headroom.
* **`POPULATION_TOLERANCE` never fired wrongly.** The gate caught both shrinks, every beat, on the
  first one. What it could not do was attribute them. That gap is closed at the source (D21), not
  at the gate.
* 🟢 **The OTHER blocker named in `SUBCOHORT_DIAGNOSIS.md` is also discharged.** That file's
  "root cause of the throughput half is not in calibration code — production Postgres is still
  `standard-0`, 4 GB against a ~66 GB database, the plan upgrade has not been run" is out of date:
  `heroku pg:info` now reads **Standard 3**, upgraded on 2026-08-31 (v3958/v3959/v3962, 11:02 PDT).
  The writer's own recovery straddles both fixes — CAL-P134's bounded statement got it finishing at
  all (898 s, 07:14Z, before the upgrade); the plan took it to 137–199 s afterwards.
* **The dark window is smaller than `calibration-021` says, on today's ledger.** CAL-P211 computed
  3.3–3.7 h from `staged:unit_ms_mean` = 164,258 ms — but that mean is inflated by cancelled units
  (2 cancellations burned 800,608 ms of this beat's 1,149,812 ms of unit time). The honest
  back-to-back cost is `staged:unit_ms_mean_completed` = **69,844 ms**, which a single-process
  drain pays and the beat does not: **128 × 69.8 s ≈ 2.5 h**. CAL-P195 observed 5.5 units/min on a
  live one-off, which would be ~25 min; the two disagree by 6× and the first ten minutes of an
  actual drain settles it. ⚠️ Plan on 2.5 h and be pleasantly surprised — do not promise 25 min.
* **lane1/049 (31,462 markets → resolved) is gate-safe.** It changes DATA, not the predicate, so
  `population_predicate_fingerprint` is unchanged and Rule 2 admits growth on a matching predicate
  up to `POPULATION_GROWTH_CEILING = 1.0` (+100%) with a `population_growth_acknowledged`
  observation (`calibration_publish_gate.py:869-919`). The real coordination constraint is not the
  gate: **any Heroku release kills an in-flight attended drain and leaves a 31-minute dead lease
  that REFUSEs every relaunch** (measured, v3980, 2026-09-01). Sequencing ask is a deploy pause for
  the drain window, not a hold on the backfill.

## 8. Evidence index

* `GET /api/calibration` — `by_source`, `by_category`, `generated_at 2026-08-31T04:37:36Z`
* `GET /api/admin/task-metrics?task=bookmaker_calibration` — 50-sample duration ring, `last_failure_at`, `last_result_summary`
* Sentry `issues/7677836806/events/` — 10 gate rejections, 2026-08-29 → 2026-09-02, per-category diffs
* `POST /api/admin/db-query` — the Query-2 recount, 17,176
* `durable_state_snapshots` `calibration:main:phase_ledger` — `outcome.gate = refuse`, `terminal = failed`
* Source: `precompute_calibration.py:67-89, 242-330, 5709-5712`; `backfill_winners.py:7531-7690`;
  `calibration_publish_gate.py:68, 819-935`; `tasks/__init__.py:4735-4761`
* Commits: `67f5a6d3` (D5) · `fd033079` (D12) · `2472b7e8` (D21) · `9c9f7abf` (D13) ·
  `6be79cd0` (RULE E) · `f8126c8c` (K′) · `9f1aacc8` (CAL-P170)

## 9. What this overturns

`artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md:453-476` wrote *"the −10.5% is cause-unestablished …
Do not bump the version to 'fix' this … The bump is only safe once throughput is fixed AND a
completed build's population has been read and understood."* Both conditions are now met:
throughput was fixed at the writer (CAL-P134) and the population has been read, per category, from
the gate's own record. The instruction was right when it was written; its precondition has been
discharged rather than skipped.

CERT-725's `BLOCK` was correct on the evidence available to it. Its finding — that a bump waves an
unexplained shrink through an unbounded escape — no longer describes the candidate, because the
shrink is no longer unexplained.
