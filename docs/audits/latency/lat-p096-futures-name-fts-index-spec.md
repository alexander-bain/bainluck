# LAT-P096 — the futures NAME arm has no FTS index, and it costs the typeahead ~3.6 s

**Cycle:** LAT-P096 · **Issue:** #1866 · **Date:** 2026-08-26 · **DDL: NOT RUN by this lane**
(ruling 131 — index DDL with no code half is Alex's attended batch, outside Alembic; gotcha #31).

**Ship this unblocks:** a person typing in the search box sees suggestions in a fraction of a
second instead of waiting ~4 s for the first one. That is the done-bar's failing half.

---

## 1. The finding

`/api/events/typeahead` spends **89–91 % of a cold request** in one stage. Measured on production
`d2169e1d` with `?debug_timing=1`, three never-asked terms:

| term | `futures_query` | total | share |
|---|---:|---:|---:|
| `eintracht` | 3,628 ms | 3,991 ms | 90.9 % |
| `kaiserslautern` | 3,510 ms | 3,913 ms | 89.7 % |
| `wolfsburg` | 3,665 ms | 4,113 ms | 89.1 % |

Corroborated by `x-timing-split` on a fourth term: `wall=4863.0; db=4766.5; app=96.5; q=5;
maxq=3909.3`. **One statement is 80 % of the wall clock**, and it is a database cost, not app time.

### What it is NOT — three candidates measured and eliminated

Ruling them out mattered, because each is the intuitive answer:

| candidate | measured | verdict |
|---|---:|---|
| the UNION candidate subquery | 112.2 / 116.6 ms cold | not it |
| the outcome-name arm (3.2 M row table) | 8.4 / 8.7 ms | not it |
| `selectinload(outcomes)` on the 20 picked markets | 130.3 ms, 97 rows | not it |

The 20 markets the `ORDER BY market_tier, volume DESC` selects have **0–21 outcomes each**, so the
eager load never fans out. Total reconstructed: ~250 ms against a measured 3,909 ms.

### What it IS

`futures_name_filter` = `FTS(name) OR name ILIKE '%q%'` (`routes/events.py`, now
`_build_futures_name_filter`). There is **no FTS expression index on `futures_markets.name`**.
Measured, `werder`, open markets only:

| shape | exec | plan | buffers | rows removed |
|---|---:|---|---:|---:|
| ILIKE alone | **27.8 ms** | Bitmap Index Scan `ix_futures_name_trgm` | 904 | 216 |
| FTS alone | **742.7 ms** | Index Scan | 27,483 | 49,551 |
| the OR (what runs) | **870.4 ms** | Index Scan | 27,483 | 49,557 |

**Two defects, one cause.** The FTS half computes one `to_tsvector` per open market because nothing
indexes it. And because it is OR'd inline, it also **defeats `ix_futures_name_trgm`** — an index
that already exists and serves the ILIKE half in 27.8 ms. The OR costs 842.6 ms over ILIKE alone
and returns, for this term, **the identical 28 rows**.

---

## 2. Why the FTS half is not simply deleted

Deleting it looks like a free 31× win. It is not, and this was checked by measuring rather than
assuming. Production recall census, open markets, ILIKE-only vs the full OR:

| term | ILIKE only | FTS OR ILIKE | delta |
|---|---:|---:|---:|
| `champions` | 405 | 598 | **+193** |
| `relegation` | 53 | 116 | **+63** |
| `chiefs` | 25 | 30 | +5 |
| `election` | 2,365 | 2,370 | +5 |
| `werder` | 28 | 28 | 0 |
| `schalke` | 34 | 34 | 0 |
| `winner` | 3,530 | 3,530 | 0 |
| `trump` | 784 | 784 | 0 |
| `fed` | 264 | 264 | 0 |
| `mvp` | 30 | 30 | 0 |

The FTS half earns its place through **stemming**: `champions` reaches "Champion", `relegation`
reaches "relegated". **Six of ten terms gain nothing**, which is precisely why removing it survives
a spot check and silently loses 193 open markets on a head query.

**A fallback shape is also wrong** and was rejected on the same numbers: "run FTS only when ILIKE
returns nothing" never fires for `champions` (ILIKE already returns 405), so all 193 rows would
still be lost. The recall gap lives *inside* a healthy result set, not at zero.

⇒ The lever is an index, not an edit. Pinned by `backend/tests/test_futures_name_filter_arms.py`,
which is red-first against both the deletion and the fallback.

---

## 3. The DDL — for Alex's attended batch

```sql
-- LAT-P096 / #1866. Attended, outside Alembic (ruling 131, gotcha #31: never
-- CREATE INDEX CONCURRENTLY in an Alembic release phase — the Heroku release
-- timeout is ~5 min).
--
-- Partial on the open-market predicate the route always ANDs on, so the index
-- covers ~50 K rows rather than the full ~730 K table.

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_futures_name_fts_open
    ON futures_markets
    USING gin (to_tsvector('english', coalesce(name, '')))
    WHERE status = 'open';
```

**The expression must match the route's byte-for-byte.** `to_tsvector('english', coalesce(name,
''))` — with the `coalesce`, with `'english'`, over `name`. A structurally-mismatched expression
index builds *valid* and is then silently never used. That exact failure was caught once already in
this program (LAT-P086, `::text` vs `CAST(... AS VARCHAR)` on the teams DDL), which is why the gate
compiles its SQL from the live ORM instead of a hand-copy.

**Why partial on `status='open'` only**, and not also on the `resolution_date` clause: the
resolution predicate is `resolution_date IS NULL OR resolution_date >= now()`, and `now()` is not
immutable, so it cannot appear in an index predicate at all.

### Verify it built valid

```sql
SELECT indexrelid::regclass AS index, indisvalid
FROM pg_index WHERE indexrelid = 'ix_futures_name_fts_open'::regclass;
```

`CREATE INDEX CONCURRENTLY` can leave an **invalid** index behind on failure, and an invalid index
is never used while still occupying disk — it looks like the DDL worked and changes nothing.

---

## 4. The gate — pre-registered, bars frozen BEFORE the index exists

```bash
source ~/.claude/.env
python3 backend/scripts/gate_futures_name_fts_index.py --label before   # exit 1, RED (recorded)
# ... attended DDL ...
python3 backend/scripts/gate_futures_name_fts_index.py --label after \
    --out docs/audits/latency/lat-p096-futures-name-fts-gate-after.json
```

**Exit 0 = GREEN. Exit 1 = RED. Any other exit is the harness failing, not a verdict** (gotcha #54
as amended — read the exit code's *value*).

Three criteria, all frozen now:

1. **SHAPE** — a `BitmapOr` over **both** `ix_futures_name_fts_open` *and* `ix_futures_name_trgm`.
   Requiring both is deliberate: the thesis is that the OR currently defeats the trigram index, so
   an "after" plan using only the new index has taken half the win. This is the criterion that
   cannot be faked by timing.
2. **BUDGET** — arm/control ratio ≤ **0.80**, against a CPU-matched control
   (`to_tsvector` over `external_id`, same table, not indexed by this DDL).
3. **SEMANTICS** — `count(*)` and `md5(string_agg(id::text, ',' ORDER BY id))` unchanged per term,
   computed **server-side**. `winner` matches 3,530 rows and `db-query` truncates at 1,000, so
   comparing extracted id lists would compare the first 1,000 of each and report an agreement it
   never checked.

**Recorded RED, 2026-08-26** (`lat-p096-futures-name-fts-red.json`): all ten terms FAIL shape and
budget, semantics PASS. Ratios median 3.41, range 1.02–4.76.

### Why the budget is a ratio and not milliseconds

Absolute cost here is per-row `to_tsvector` CPU, and host contention swings it several-fold within
minutes. Measured while setting the threshold, interleaved:

```
arm_ms:  4552.7 3627.7 4736.9 1871.3 790.9 772.9 997.8 4737.4 4843.9   (6.3x spread)
ratio:      2.66   3.27   2.81   4.88  3.26  3.59  4.05   3.13   3.30   (1.8x spread)
```

A millisecond threshold against a quantity that moves 6.3× on its own is a coin flip. This is the
same correction `gate_teams_fts_index.py` already carries.

⚠️ **The honest margin is thinner than the median suggests.** `fed` recorded a red ratio of **1.02**
(its control happened to be slow in the same round), so 0.80 sits only 1.28× below the tightest red,
not the ~3× the other nine imply. The threshold is kept at 0.80 because the predicted post-DDL value
is ~0.05 — but an "after" reading between 0.80 and 1.02 on a single term is **noise on a thin
margin**, to be re-run with more rounds, never reported as a near-miss win.

### If the shape criterion fails but the budget passes

That means the planner took the FTS index and left the ILIKE half scanning. Do **not** call it a
pass. Half the mechanism this spec describes is then unconfirmed, and the remaining scan is the part
that already had an index available.

---

## 5. What this is NOT, and the precedent that says so

LAT-P088 proposed a **trigram** index for this table (`ix_futures_name_trgm_open`). It built valid,
was chosen 8/8, preserved semantics — and **failed its budget and was dropped**, because trigram
selectivity dies on high-frequency terms (`world series` 0.083, `super bowl` 0.078, but `winner`
0.979, `election` 0.998). Fable's 2026-08-25 note drew the conclusion: *"your next lever needs to
work on common-word queries specifically."*

This lever is a different instrument and the distinction is the reason to expect a different
outcome. The trigram gate failed on **selectivity** — the index existed and could not narrow a
common term. Here there is **no index at all**, so every term, common or rare, pays a full scan of
every open market. The failure mode is not "the index cannot narrow this term", it is "nothing is
indexed".

That said, the same suspicion is designed into the gate rather than argued away: the term set
carries `winner`, `trump` and `fed` explicitly labelled `high-frequency`, so a GREEN that holds only
on rare terms cannot happen quietly. If the common terms fail the budget while the rare ones pass,
that is the trigram result reappearing in a new index type, and the honest response is the same one
Alex took last time — drop it.

---

## 6. Expected payoff, stated as a prediction so it can be wrong

- The arm falls from ~870 ms to a bitmap scan of tens of rows (~20–40 ms), and the ILIKE half gets
  `ix_futures_name_trgm` back.
- `futures_query` is 89–91 % of a cold typeahead, so the cold first-touch p50 should move from
  **~4,013 ms** (n=5 never-asked terms, measured today) toward the several-hundred-ms range.
- This does **not** by itself meet the done bar, and the report says so. It removes the dominant
  stage; what is left has not been measured on the post-index shape and no claim is made about it.

**Provenance:** LAT-P096, 2026-08-26. Related: #1866, #1916, #993, #1545. Prior art:
`lat-p086-teams-fts-index-spec.md` (GREEN), LAT-P088's futures trigram gate (RED, dropped).
