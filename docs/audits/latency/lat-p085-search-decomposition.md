# LAT-P085 — `/api/events/search` decomposition and the costed lever

Measured 2026-08-24, production, against master `b5c2a750` (v3886, deployed 17:23:50Z).
All timings taken **after** that release, so no window straddles a deploy.

---

## 0. The charter headline, clean

Taken **sequentially**, one endpoint at a time, nothing else of this session's in flight
(ruling 127: a census that samples every request counts the observer).

| surface | n | p50 | p90 | max | note |
|---|---|---|---|---|---|
| `/api/feed?limit=20` | 14/14 ok | **372.0 ms** | 389.3 | 441.4 | 20 items every sample |
| `/api/typeahead` | 25/25 ok | **231.3 ms** | 2220.2 | 3522.8 | warm-only p50 230.1 |
| `/api/events/search` | 40/40 ok | **821.7 ms** | 1493.5 | 1605.4 | 90% over the 500 ms bar |

Two things the typeahead row says that the p50 alone does not:

* The **transport floor is 230.9 ms** and the warm p50 is 230.1 ms. Warm typeahead server
  time is therefore ~0 ms — the number a user feels is *entirely* network. There is no
  server-side win left on the warm path; only the cold rate can move.
* Cold rate was 6/25 here vs 3/48 in LAT-P084. **These are not comparable.** This run used
  the 5-term floor set × 5 rounds, whose design floor is 5/25 = 20% (one unavoidable cold
  per term per TTL window); LAT-P084 used 8 terms × 6 rounds, floor 8/48 = 16.7%, and
  measured *below* its floor because prior traffic had pre-warmed some keys. Quoting
  24% vs 6.2% as a regression would be a term-set artifact, not a finding.

---

## 1. Where the milliseconds go

40 clean samples, `?debug_timing=1`, share of the **server** total:

| stage | p50 ms | p90 ms | share |
|---|---|---|---|
| **teams** | 159 | 401 | **40.4%** |
| **futures** | 142 | 358 | **30.4%** |
| event_page | 55 | 109 | 10.6% |
| event_count | 42 | 122 | 10.4% |
| event_odds_query | 21 | 57 | 4.3% |
| event_gei | 0 | 0 | 1.5% |
| event_teams | 0 | 0 | 1.5% |
| futures_format_concepts | 4 | 7 | 0.7% |
| **event_odds_aggregate** | 0 | 3 | **0.2%** |

Server p50 464 ms; **residual p50 292.8 ms** (transport + JSON serialisation).

### The three named hypotheses, answered

* **FTS ranking — NO.** The `Sort` node carrying `ts_rank_cd` is 0.0–2.6 ms across every
  plan measured. Ranking is 0.1% of the futures arm and 0.6% of the teams arm.
* **Correlated aggregation — NO.** `event_odds_aggregate` is 0.2%; #993's non-correlated
  `IN` already removed this cost. It is not worth revisiting.
* **ILIKE breadth — YES, but it is the *second* problem, and its mechanism is I/O.** See §3.

### The first-order answer is a stage nobody had looked at

`teams` is the largest single consumer of the search budget and had not appeared in any
prior latency cycle's decomposition.

---

## 2. THE LEVER — the `teams` stage is a seq scan of `to_tsvector` CPU

`teams` is **9,240 rows / 9.4 MB heap / 5.5 MB indexes**. It is small enough to be
permanently resident; it does no I/O at all. Every millisecond it spends is CPU.

`_build_team_search_filter` (`app/routes/events.py:1566`) is an OR of three
`to_tsvector(...) @@ websearch_to_tsquery(...)` arms over `name`, `abbreviation`, and
`alternate_names::text`. `_team_search_vector` (`:1152`) then rebuilds all three, wrapped
in `setweight`, for the `ts_rank_cd` in the SELECT list and ORDER BY. That is **six
`to_tsvector` constructions per row — one of them a JSONB→text cast — evaluated ~9,240
times per search request**, roughly 55,000 tsvector builds per keystroke-driven query.

None of it is indexable today. `teams` carries a trigram GIN on `name` and a
`jsonb_path_ops` GIN on `alternate_names`; **neither can serve an FTS `@@` predicate.**

### Measured RED (production, `EXPLAIN (ANALYZE, BUFFERS)`, 2026-08-24)

| term | exec ms | plan | blocks | rows out | rows filtered |
|---|---|---|---|---|---|
| yankees | 485.5 | **Seq Scan** | 1,156 | 2 | 9,238 |
| celtics | 459.5 | **Seq Scan** | 1,156 | 5 | 9,235 |
| red sox | 470.3 | **Seq Scan** | 1,156 | 3 | 9,237 |
| world cup | 386.0 | **Seq Scan** | 1,156 | 0 | 9,240 |

The `Sort` self-time in these plans is 0.0–2.6 ms. **100% of the cost is the scan.**

**The cleanest proof available:** `world cup` returns **zero rows** and still burns
385.9 ms. The cost is entirely independent of the result set. And across the eight
headline terms, **five return zero teams** — the stage spends 40% of the search budget
producing nothing on 62% of the headline set.

### Proposal — three FTS expression indexes on `teams`

```sql
CREATE INDEX CONCURRENTLY ix_teams_fts_name ON teams
  USING gin (to_tsvector('english', coalesce(name, '')));
CREATE INDEX CONCURRENTLY ix_teams_fts_abbrev ON teams
  USING gin (to_tsvector('english', coalesce(abbreviation, '')));
CREATE INDEX CONCURRENTLY ix_teams_fts_altnames ON teams
  USING gin (to_tsvector('english', coalesce(alternate_names::text, '')));
```

**Three indexes, not one combined vector — and the reason is semantics, not taste.**
A single index on `setweight(name) || setweight(abbrev) || setweight(alt)` would let the
OR collapse to one `@@`, which is cheaper still — but it **widens recall**: the tsquery
`'red' & 'sox'` currently requires both lexemes in the *same* column, whereas against a
concatenated vector it would match a team with `red` in `name` and `sox` in
`alternate_names`. This filter exists precisely to kill cross-matching noise
("super bowl" → Bowling Green Falcons, "messi" → ACR Messina). Three separate indexes let
the planner build a **BitmapOr of three index scans with the predicate unchanged**, so the
result set is provably identical.

The `ts_rank_cd` projection needs no change: once the scan returns 0–5 rows instead of
9,240, the ranking CPU dies with it.

**Cost.** Three GINs over 9,240 short tsvectors: est. **3–6 MB total** (the existing
`ix_teams_name_trgm` is 2.3 MB over the same rows). Build via
`CREATE INDEX CONCURRENTLY` in `psql` per gotcha #31 — **not** in the Alembic chain
(`migration_slot: none` this cycle regardless). On 9,240 rows each build is seconds.
Rollback is `DROP INDEX CONCURRENTLY`, instant, and needs no code revert: **the index is
useful with the current query text unmodified**, so there is no code change to gate. That
is the unusual and attractive property of this lever — it is a pure DDL addition with an
unmodified application.

**Expected payoff, stated as a prediction so it can be refuted.** Seq Scan → BitmapOr;
teams stage p50 159 → single-digit ms; server p50 464 → ~305 ms; **wall p50 821.7 → ~660 ms.**
That does **not** clear the 500 ms bar and I am not going to claim it does — the residual
transport floor is 292.8 ms, so the entire server budget available under a 500 ms wall is
~207 ms. This lever buys the largest single share of the way there and nothing more.

### Red-first gate (pre-registered)

The RED table above **is** the gate's red half, already banked. GREEN requires all three:

1. **Plan flip** — the `teams` node is a Bitmap Heap Scan (or BitmapOr), not a Seq Scan,
   on all four specimens.
2. **Budget** — exec_ms < 50 on all four.
3. **Semantics unchanged** — the returned `teams.id` sets are *identical* to the red run's
   for all eight headline terms. Baseline captured at
   `docs/audits/latency/lat-p085-teams-red.json`; the zero-row terms
   (world cup, stanley cup, nba champion, masters winner, world series) must **stay** zero.

Criterion 3 is the one that matters. A faster stage that returns different teams is a
product regression wearing a latency win.

---

## 3. The runner-up, and a correction to the prior art

`futures` is 30.4%. Decomposed across six `EXPLAIN ANALYZE`'d futures arms (2,732.7 ms of
self time): **69.0% is I/O read wait, 31.0% CPU.** The bitmap index scans are fast; the
**bitmap heap scan** is where it goes, fetching pages for resolved history it then throws
away.

Measured discard, and the heap pages that discard costs:

| term | candidate rows | heap pages | open rows | open pages | page reduction |
|---|---|---|---|---|---|
| world cup | 3,252 | 1,805 | 261 | 125 | **14.4×** |
| yankees | 1,781 | 778 | 16 | 16 | **48.6×** |
| fed | 1,292 | 1,005 | 253 | 203 | 5.0× |
| celtics | 584 | 202 | 0 | 0 | ∞ |
| nba champion | 9 | 9 | 5 | 5 | 1.8× |

The 1,805-page figure for `world cup` was computed independently (`count(DISTINCT
(ctid::text::point)[0])`) and the plan's own heap scan reported 1,834 blocks — two methods
agreeing, so the model is validated rather than asserted.

`futures_markets` is now **5.68% open** (48,814 of 860,282) against 11.8% when #1731 sized
this. Objects in play total **2,767 MB against a 1,024 MB `shared_buffers`**, so nothing
stays resident.

**The correction the next cycle needs.** #1731's decision B was a *partial GIN trigram*
index `WHERE status='open'`, ruled GO by Alex on 2026-08-12. LAT-P041 then built
**`ix_fm_open_search_cover`, a btree** — `btree (name, resolution_date, id) INCLUDE (...)
WHERE status='open'` — measured it net-negative, and rolled it back. A btree on `name`
**cannot serve `ILIKE '%x%'` at all**; it degenerated into an index-only scan over every
open row. Worse, two of that A/B's three specimens (`la`, `re`) are two-character infixes
that pg_trgm is definitionally blind to (`%x%` needs 3+ alphanumerics). **The refutation
used an object the proposal did not name and specimens the mechanism cannot serve.** The
partial GIN of decision B has never been built or measured. At today's open fraction it
would be ~10–12 MB — small enough to stay resident permanently.

I am recording that, not proposing it. The directive asked for the single biggest lever;
that is §2. This is the measured runner-up, with its prior art corrected so the seventh
visit to this question does not start from a false refutation.

---

## 4. A cheap secondary, honestly sized

`futures_markets` reloptions are `{autovacuum_analyze_scale_factor=0.02,
autovacuum_analyze_threshold=5000}` — #1794 tuned the **analyze** side and confirmed it
honoured. The **vacuum** side was never touched: it still runs at the global
`autovacuum_vacuum_scale_factor=0.2`, so autovacuum does not fire until
`50 + 0.2 × 860,282 = 172,106` dead tuples. The table currently sits at **128,183 dead
against 860,282 live (14.9%)** — 74% of the way to its own trigger, which is its normal
steady state.

So the heap every bitmap scan walks is routinely ~15–20% larger than it needs to be.
That is real and the fix is one reloption, but **it is a ~15% cut where §2 is a ~40% cut
and §3 is 5–48× on pages fetched.** It is a secondary, and calling it a lever would be
inflating it.

---

## Artifacts

| file | what |
|---|---|
| `lat-p085-search-clean.jsonl` | 40 clean `/api/events/search` samples with stage vectors |
| `lat-p085-search-contaminated.jsonl` | 64 samples taken while this session ran `EXPLAIN ANALYZE` — kept as the ruling-127 specimen (see below) |
| `lat-p085-feed-clean.json` | 14 `/api/feed` samples |
| `lat-p085-typeahead-clean.jsonl` | 25 `/api/typeahead` samples |
| `lat-p085-teams-red.json` | teams-stage result sets — the semantics half of the red-first gate |

### The contamination specimen is worth keeping

The contaminated series did not merely inflate the numbers — it **reordered the ranking**:

| stage | contaminated share | clean share |
|---|---|---|
| futures | **65.4%** | 30.4% |
| teams | 12.6% | **40.4%** |

Because this session's `EXPLAIN ANALYZE` traffic hammered exactly the `futures_markets` /
`futures_outcomes` tables, the observer inflated the stage it was observing until that
stage looked like the answer. A decomposition taken from the contaminated series would
have aimed the entire cycle at the #2 stage with high confidence. Ruling 127 says a census
that samples every request counts the observer; this is the sharper corollary — **the
observer does not add a constant, it adds a constant *to whatever it touches*, and a
decomposition is a ranking, so a biased constant is a wrong answer, not a noisy one.**
