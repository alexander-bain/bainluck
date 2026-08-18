# Matching Methodology Audit — every constant, threshold, and precedence rule in market↔event matching, team resolution, and dedup/merge

*Branch `codex-adhoc/matching-audit` from `a6665b14` (frozen cohort-views head untouched), worktree `matching-audit`, 2026-08-18. Artifacts only, read-only. Same rigor/format as `METHODOLOGY_AUDIT.md`: every assumption as CHOSEN / ALTERNATIVE / EVIDENCE (code cite + light-API/incident numbers where available) / VERDICT (sound | suspect | wrong) / the experiment that settles it. Specimen set = this week's incident corpus; each incident is EXPLAINED by a numbered assumption, and any unexplained incident is a finding. Ranked by expected incident-rate impact.*

*Pre-read: `event_registry.py` (unified `find_or_create_event`), `prediction_market_matching.py` (hourly link), `team_identity.py` (canonical team resolve), `statpal_sync.py`/`espn_sync.py` (ingest clocks), `utils/team_binding_invariant.py` (identity lens).*

---

## How to read

A matching system either **joins the right two rows** or it **doesn't** — there is no 0.5pp hedge. The calibration audit could tolerate 1–2pp slop; this one cannot — a wrong absorption is invisible, a duplicate is noisy but reversible. Ruling 048 made that asymmetry explicit: `event_registry.py:15` “a duplicate is visible and reversible, a wrong absorption is neither.” Every constant below is on the wrong-absorption side of that trade.

---

## Ranked findings (high → low expected incident-rate)

| Rank | Assumption | Verdict | Incident(s) it explains | Gate experiment |
|---|---|---|---|---|
| 1 | **Index layer blind trust — `team_identity_mapping` exact-match indexes with no write-time validation** | **wrong** | Shared `espn_id` across real games (same provider id on two `events` rows) + long-tail eponymous-team cross-league alias drift (e.g., Panthers NFL/NHL) | Index census SQL (§5) |
| 2 | **Clocks — provider timezone assumptions per namespace (all namespaces lie in at least one place)** | **wrong** | StatPal Eastern-as-UTC namespace (§4) + Kalshi date-only ticker 0↔100 vs UTC commence + 2,069 ticker-vs-event date disagreements | Clock census SQL (§4) |
| 3 | **ID precedence — external_id / espn_id / statpal_fixture_id / ticker who wins when they disagree, per path** | **suspect** | Shared `espn_id` across games (Step 1 wins on stale `espn_id`) + 2,069 ticker-vs-event disagreements (ticker date loses to event commence, but no rule says who is authority) + Kalshi/Polymarket no direct ID column (Step 1 absent) | Precedence matrix curl (§2) |
| 4 | **Name matching — every place a display label or fuzzy name licenses a bind/merge** | **suspect** | Post-ruling-042 label equality is not identity; residual fuzzy `names_match` on mapping & team tables + `_fuzzy_score 40–60` containment/mascot + prediction-market auto-create label absorption pre-048 | Label census grep (§3) |
| 5 | **Time windows — ±28h structured-match window + 21600s (6h) absorption/dedup separation** | **suspect** | Doubleheader same-slug absorption (12:05 vs 18:40) + consecutive-day series + cross-timezone UTC-boundary series + 177-event collapsed-timestamp slate on 2026-07-13 (sibling beyond LIMIT 30) | Window distribution SQL (§1) |

---

## 1. TIME WINDOWS: the ±28h structured-match window, the 21600s absorption separation, any other duration constant — derived from what? What does the real schedule distribution say each should be?

### CHOSEN

* **±28h structured-match window** — `event_registry.py:67` ` _MATCH_WINDOW = timedelta(hours=28)  # Wide enough for cross-source date disagreements (Kalshi settlement vs game start)` and `services/event_registry.py:65` comment + `sports.py:822/846` `_WINDOW_SEC = 28*3600`, `prediction_market_matching.py:171/320` “date-only tickers sit up to ~28h off”, `espn_helpers.py:23` “28h structured match”. The window is *date-disagreement* derived — Kalshi settlement dates are calendar-date strings with no time, so a ticker dated `26JUL11` legitimately sits `±24h` from the event's UTC `commence_time`, plus 4h of cross-timezone slop (gotcha #14). The window holds `±28h` and is consumed twice: (a) `event_registry.py:329` `commence_time.between(commence-28h, commence+28h)` for `find_or_create_event` Step 3, ordered by `abs(epoch diff)` and capped `LIMIT 500`; (b) prediction-market linking `prediction_market_matching.py:1540` same 28h for date-only ticker tolerance.

* **21600s (6h) absorption/dedup separation** — `sports.py:616` `ABS(EXTRACT(EPOCH ...)) < 21600`, `admin_events.py:386/561`, `admin_backfill_linkage.py:84` `time_diff > 21600`, `snapshot_sparsity.py:408` `>21600`. The 6h constant is the **anti-absorption** separation: two `events` rows with the *same* sport + same team names but whose `commence_time` are **≥6h apart are not the same game** — they are a doubleheader / consecutive-day series / cross-timezone UTC-boundary pair. The admin dedup rails and the merge guards refuse to merge rows that are ≥6h apart (`sports.py:616` `a.commence_time - b.commence_time <21600` is the *candidate* set; `admin_events.py:561` `keeper vs orphan <21600` is the *merge* gate). `prediction_market_matching.py:2194` even asserts `18000 < delta <21600` (5–6h apart) as the doubleheader specimen.

* **Other windows in the tree** — `date_noon ±18h` in `event_registry.py:485` audit (`date_noon = strptime("%Y%m%d",12:00 UTC) ±18h` = 36h date bucket for count-vs-ESPN), `SCORE_TTL_S=21600` (`precompute_interestingness.py:99`, unrelated), `CACHE_TTL=21600` (`source_intelligence.py:34`), `PROV_AGE 21600` provenance test (`test_sentinel_durable_evidence_298.py:193`), `GOLF_PLACEHOLDER_HIGH_BAND=0.80` etc. are not time windows. The only *matching* durations are 28h and 6h (plus the implicit `±18h` date audit).

### ALTERNATIVE

Derive windows from the **schedule distribution**, not from ticker slop. The specimen that should set them is not "how far Kalshi's calendar date can be from UTC" but "how close two *different* real games between the same clubs can be, and how far the *same* game can legitimately drift across sources." Alternatives articulated in code: a **two-window design** — a narrow `±6h` window for sources that carry a real clock (ESPN `commence_time`, Odds API `commence_time`, StatPal fixture time once timezone-corrected) and a wide `±28h` *only* for date-only ligatures (Kalshi ticker date). A second alternative is **no window at all for id-anchored joins**: Step 1 shared-id absorbs without a window, Step 3 dereferenced-id absorbs with the names but its time comes from its own schedule (`schedule_derived=True`), so the window is only a *candidate filter*, not an identity rule. Ruling 048's gate already makes the window non-identity: an unanchored claim never reaches it (`event_registry.py:242` `if not schedule_derived: return None`).

### EVIDENCE — code

`event_registry.py:65:67` 28h comment and constant; `event_registry.py:326:342` `between(...-28h, ...+28h)` + `order_by(abs(epoch diff))` + `limit 500` (was 30, hit 177 collapsed-timestamp slate 2026-07-13 `#1085`); `sports.py:616,822,846` 28h/6h pair; `admin_events.py:386/561` and `admin_backfill_linkage.py:84` 6h dedup gates; `prediction_market_matching.py:171/320` 28h ticket tolerance; `espn_helpers.py:23` 28h time-loose write paths. **Schedule distribution the code itself observed:** NCAA baseball 2026-07-13 had **177 events on one collapsed `now` timestamp** (prediction-market auto-create fallback `now` — gotcha #14), which forced `_STRUCTURED_MATCH_CANDIDATE_LIMIT` from 30→500 and the `ORDER BY time-proximity` (`event_registry.py:72:85`). That is not a schedule — it is a pathology — and it proves the window can hold a full day's slate for one sport.

**Light-API / incident numbers:** No light endpoint directly measures windows, but the incident corpus does: (a) shared `espn_id` across games — the 6h separation is supposed to keep them apart, but Step 1 shared-id absorption has *no* window and would join them before the 6h gate is ever checked; (b) 2,069 ticker-vs-event date disagreements — the union of ticker date vs event commence has a long tail to `24–28h` because tickers carry settlement *date* while events carry game *time*; (c) doubleheader specimen `TST_SPORT_001_DH` (`test_event_registry.py:514` ±28h boundary + `test_prediction_market_matching.py:2194` 5–6h apart).

### VERDICT

**suspect**, with one leg sound, one leg derived from the wrong distribution. The 28h window is sound *as a candidate filter* (it contains the same-game sibling even with Kalshi calendar slop) but it is derived from **ticker slop, not schedule closeness** — it is `±28h` because `~28h` is the date-only drift, not because `28h` is how far two different real games between the same clubs must be apart. The 6h separation is the real schedule constant (doubleheader 5–6h, consecutive-day ~18–24h, cross-timezone UTC-boundary 1h), and 6h is plausible as the anti-absorption floor — but it is asserted, not measured. Ruling 048's gate mitigates the worst of a wide window (unanchored claims never enter it), yet a wide window still expands the *candidate set* for anchored claims — 177 on one timestamp proves that set can be pathology-large, and raising the cap to 500 papers over the pathology without fixing the `now` collapse at the write side.

### THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, header-only (one-off dyno, read-only)

```sql
-- Real schedule closeness: for each SAME matchup (same sport, same home/away pairing either orientation)
-- what is the MIN interval between two DISTINCT scheduled/completed events? This is the anti-absorption floor.
WITH pairs AS (
  SELECT sport_id,
         LEAST(home_team_name, away_team_name) || ' vs ' || GREATEST(home_team_name, away_team_name) AS matchup,
         commence_time,
         LEAD(commence_time) OVER (PARTITION BY sport_id, LEAST(home_team_name, away_team_name), GREATEST(home_team_name, away_team_name) ORDER BY commence_time) AS next_time
  FROM events
  WHERE status IN ('scheduled','live','completed','closed')
)
SELECT
  CASE WHEN EXTRACT(EPOCH FROM (next_time - commence_time))/3600 < 6 THEN '<6h (doubleheader)'
       WHEN EXTRACT(EPOCH FROM (next_time - commence_time))/3600 < 12 THEN '6–12h'
       WHEN EXTRACT(EPOCH FROM (next_time - commence_time))/3600 < 24 THEN '12–24h (consecutive-day)'
       ELSE '≥24h' END AS bucket,
  COUNT(*) AS pairs,
  MIN(EXTRACT(EPOCH FROM (next_time - commence_time))/3600) AS min_h,
  PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (next_time - commence_time))/3600) AS p1_h
FROM pairs WHERE next_time IS NOT NULL
GROUP BY bucket ORDER BY MIN(EXTRACT(EPOCH FROM (next_time - commence_time)));

-- Same-game cross-source drift: for events that have ≥2 source ids, what is the drift between the source ingest times?
-- Proxy: ticker date vs event commence for the 2,069 linkage disagreements — what should the window have been?
SELECT
  CASE WHEN ABS(EXTRACT(EPOCH FROM (ticker_date - commence_time)))/3600 < 12 THEN '<12h'
       WHEN ABS(EXTRACT(EPOCH FROM (ticker_date - commence_time)))/3600 < 24 THEN '12–24h'
       WHEN ABS(EXTRACT(EPOCH FROM (ticker_date - commence_time)))/3600 < 28 THEN '24–28h'
       ELSE '≥28h (would have missed)' END AS drift_bucket,
  COUNT(*) FROM (
    SELECT e.commence_time, (m.ticker::date)::timestamp AS ticker_date
    FROM futures_markets m JOIN events e ON e.id=m.event_id
    WHERE m.source='kalshi' AND e.commence_time IS NOT NULL
  ) s
GROUP BY drift_bucket ORDER BY MIN(ABS(EXTRACT(EPOCH FROM (ticker_date - commence_time))));
-- Expectation: drift 24–28h mass is the ticker slop that justifies 28h; matchup p1 <6h mass is the doubleheader that justifies the 6h anti-absorption floor. The two-window design is then 28h for date-only ligatures, 6h for real-clock sources.
```

---

## 2. ID PRECEDENCE: when external_id, espn_id, statpal_fixture_id, and ticker disagree, who wins, per code path — and is it the same answer in every path?

### CHOSEN

There is **no single precedence** — there are four precedence rules in four paths, and they disagree with each other.

| Path | Who is searched, in what order, and who overwrites whom | Cite |
|---|---|---|
| **Event creation `find_or_create_event` Step 1** | Exact source-id: `odds_api→external_id`, `statpal→statpal_fixture_id`, `espn→espn_id`; kalshi/polymarket: **no** Step 1 column at all (`event_registry.py:268:282` `return None` for them). First writer's id stays; `_attach_claim` is idempotent and refuses to overwrite `external_id` if already set (`:374:380` logs “already has external_id=…, incoming=… (same game, different API ID)” and keeps the first). | `event_registry.py:268:286`, `:371:386` |
| **Event creation Step 3 fallback** | No cross-source id search as a distinct step — comment says “This step is implicit — Step 3 will find it by sport+date+teams” (`:229:232`). So an `espn_id=X` row created by Odds API is found *only* if `names_match` + 28h finds it — not by a direct `espn_id` column read from the claim's `espn_id`. The id itself is not the join key on the fallback; the **dereferenced** teams/date are. | `event_registry.py:229:232` |
| **Field update `_update_fields_by_priority`** | `espn(3) > statpal(2) > odds_api(1) > kalshi/polymarket(0)` (`:56:63`). Higher-priority overwrites `home_team_name/away_team_name/commence_time`; lower-priority never overwrites. But there is a guard: refusing to move `commence_time` to a value **after** `completed_at` (`:405:424` `#46 invariant`), because that inversion means the higher-priority source's time was folded onto the **wrong sibling**. | `event_registry.py:56:63`, `:389:424` |
| **Prediction-market linking `prediction_market_matching.py`** | Own 3-phase: Link Pass1 ticker scan + Pass2 general scan → Re-validate (Phase 1.5) → Snapshot. Ticker is a **date-only** ligature (`KXNHL… 26JUL11`) that sits `~28h` off UTC commence (`:171,320`). Ticker-vs-event date handled by gotcha #14 — ticker date is not authority, event `commence_time` is, but the code still *links* on ticker prefix + team-name fallback (`category="game_prop"` or team names + ticker prefix). No single precedence: ticker + names together license the FK `event_id`. | `prediction_market_matching.py:171/320/1540`, `:2298` absorption cost note |
| **Team resolution `team_identity.py`** | `TeamIdentityService: source_id (exact) > source_name (exact) > fuzzy mapping table > fuzzy teams table` (`:8:10`, `:45:110`). Source_id exact is king; name is fallback with auto-registration (`:110:132`). | `team_identity.py:8:10`, `:45:132` |

**When they disagree (the specimen):** a row carries `external_id=A` (Odds API) and `espn_id=B` (ESPN), and a fresh StatPal claim arrives as `statpal_fixture_id=C` for the *same* real game but with a *different* `commence_time` (Eastern-as-UTC drift). Step 1 looks up `statpal_fixture_id=C` — miss. Step 3 dereferenced match finds the existing row by `sport+28h+names_match` (because StatPal's `schedule_derived=True` from its own fixture schedule) — hit — then `_attach_claim` writes `statpal_fixture_id=C` (`:382:383` no conflict log, just `if not …: set`) and `_update_fields_by_priority` tries to overwrite commence because `statpal(2) > odds_api(1)`. So **StatPal's Eastern-as-UTC clock wins over Odds API's clock** until someone notices — and the `#46 inversion` guard (`:412` `commence_correction_inverts_completion`) is the only thing that stops it *after* the event has completed. Before `completed_at`, the wrong clock is absorbed.

The 2,069 ticker-vs-event cases are the prediction-market twin: ticker says `26JUL11`, event says `2026-07-11 23:07 UTC` (19:07 Eastern). The ticker date `2026-07-11` and the event time `2026-07-11 23:07 UTC` *agree* on the calendar, but the **provenance of the date is not the same**: ticker's `26JUL11` is a **settlement-date** string (Kalshi) with no time, event's `23:07 UTC` is a **start time**. The linker treats them as same-day by tolerance — but no path records *who was authority* when they disagreed by >24h.

### ALTERNATIVE

One precedence table for all paths, with **id authority by namespace**: `statpal_fixture_id` is authority for StatPal clocks, `espn_id` for ESPN clocks, `external_id` for Odds API clocks, and **ticker is never authority for time** (ticker's date part is settlement, not start — `prediction_market_matching.py:171` already says date-only tickers legitimately sit `~28h` off, so the ticker must not win a time fight). A second alternative is **time authority = commence_time_source**, not `sport_priority`: whoever wrote `commence_time_source` defends their time until a *higher time authority* (not higher sport priority) arrives. The current `espn>statpal>odds_api` is sport priority confounded with time authority.

### EVIDENCE — code + specimen

`event_registry.py:56:63` priority map (kalshi/polymarket have `0`, but they have **no Step 1 column at all** — so prediction-market claims *always* fall through to Step 3 and are gated by `schedule_derived`, which is `False` by default for label-parsed claims ` :116 ` — correct per ruling 042, but it means **every** Kalshi ticker-derived claim is `unanchored` and `CREATES` a duplicate until the id arrives, which is the declared cost); `event_registry.py:268:386` Step 1 and `_attach_claim` no-overwrite of `external_id` vs blind set of `statpal_fixture_id`/`espn_id`; `event_registry.py:405:424` `#46 invariant` guard; `prediction_market_matching.py:171/320/1540` 28h ticker tolerance; `team_identity.py:8:10` team precedence. **Incident numbers:** shared `espn_id` across real games — Step 1 `espn_id` equality would absorb them without any window or names check, and only the 6h separation downstream (admin dedup `admin_events.py:561`) can later split them; 2,069 ticker-vs-event date disagreements — union shows the same game has two dates; StatPal Eastern-as-UTC — `statpal(2) > odds_api(1)` means the lying namespace wins.

### VERDICT

**suspect**. The multiplicity is the bug: two of the four “who wins” answers are **silent** (Step 3 has no direct cross-id lookup, ticker time is not compared to event time per a precedence table), and the one that is explicit (`_SOURCE_PRIORITY`) conflates **who may rename the teams** with **who may move the clock**. The result is path-dependent: whether StatPal's Eastern-as-UTC lie survives depends on whether the claim reached Step 3 before `completed_at` was set — the same data produces a different event row depending on ingest order.

### THE ONE EXPERIMENT THAT SETTLES IT — matrix, header-only read-only

```sql
-- For every event that carries ≥2 of (external_id, espn_id, statpal_fixture_id), do the source_id-implied matchup/time agree with the stored row?
WITH multi AS (
  SELECT id, external_id, espn_id, statpal_fixture_id, sport_id, home_team_name, away_team_name, commence_time, commence_time_source
  FROM events WHERE (external_id IS NOT NULL)::int + (espn_id IS NOT NULL)::int + (statpal_fixture_id IS NOT NULL)::int >= 2
)
SELECT
  commence_time_source AS winner_source,
  COUNT(*) AS events_with_2_ids,
  COUNT(*) FILTER (WHERE external_id IS NOT NULL AND espn_id IS NOT NULL) AS odds_and_espn,
  -- The clock fight is visible here: distinct commence_time_source values imply the same game's time moved.
  COUNT(DISTINCT commence_time_source) FILTER (WHERE external_id IS NOT NULL AND statpal_fixture_id IS NOT NULL) AS odds_vs_statpal_distinct
FROM multi GROUP BY commence_time_source ORDER BY events_with_2_ids DESC;

-- Per-path outcome twin: for the 2,069 ticker-linked outcomes, who would have won if ticker time were authority vs event time?
-- Read the already-shipped mismatch census: SELECT ticker, commence_time, ticker_date, ... FROM futures_markets m JOIN events e ON m.event_id=e.id WHERE ABS(EXTRACT(EPOCH FROM (ticker_date - e.commence_time)))>86400
-- Expectation: no row should have >6h ticker-vs-event drift where both sides claim to be start time — ticker drift is settlement vs start, so event startup wins.
```

---

## 3. NAME MATCHING: every place a display label or fuzzy name licenses a bind or merge — post-ruling-042, label equality is not identity; census what still trusts it.

### CHOSEN

Ruling 042 (“dereference the id, never the label”) and ruling 048 (“an id-less claim never absorbs”) declare label equality is **not identity**. The code is half-migrated toward that:

* **Event registry Step 3** uses `names_match` (the only remaining label-trusting gate) but it is **gated to id-anchored claims only**: `event_registry.py:242` `if not schedule_derived: return None` and `::313` `AssertionError` if the matcher is called unanchored. `names_match` is invoked as `names_match(home_team, candidate.home_team_name) and names_match(away_team, candidate.away_team_name)` plus swapped (`:352:357`) — both teams must fuzzy-match after `name_normalization.normalize_name`. So a display label can license a **find**, but only when the **same claim's id** gave the time and teams their authority.

* **Team resolution** still trusts labels broadly: `team_identity.py:10` pipeline is `exact (source,source_id) → exact (source,source_name) → fuzzy mapping.source_name → fuzzy teams.name/alternate_names`, with auto-registration on fuzzy hit (`:110:132` `register_team_identity` on step 3/4). `_fuzzy_score` is `exact 100 → containment 60 (len≥4) → mascot last-word 40` (`team_identity.py:25:40`). Auto-registration means **a single fuzzy win becomes a future exact**: the mapping table grows on every mascot match, and the next lookup for the same label is `exact (source,source_name)` and bypasses fuzzy scoring entirely — the error is now cached.

* **Legacy / pre-042 sinks** — `utils/team_binding_invariant.py:18` “the INDEX it reads is poisoned: `team_identity_mapping` holds `source='legacy_slug'` rows…”, `enrich_markets.py:1112/1162` “falls back to `team_identity_mapping` for source-specific names”, `entity_registry.py:255` “every distinct `team_identity_mapping.source_name` … are read-only here” but treated as authority. These are **index-trusting** paths: they read the poisonable index as if it were validation. `admin_teams.py:100` and `team_merge.py:270` `UPDATE team_identity_mapping SET team_id = :target WHERE team_id = :source` is the merge-time mutation of that same index — and `team_identity_backfill.py:1` performed a one-time backfill of it from existing data (so any pre-backfill fuzzy error became permanent).

### ALTERNATIVE

Label equality licenses **nothing** beyond `names_match` inside the Ruling 048 gate, and `names_match` licenses **finding, not creation**. Alternatives post-042 that are already in code: (a) the `unanchored` tag (`_TAG_UNANCHORED` `:93`, written on every `CREATED` row) makes the label-derived event *countable* as a duplicate that reconciliation drains; (b) the `dedup_by_merge_group` (`related_futures.py:28`) dedup on `merge_group` after the fact (not a bind). The unwritten alternative for team resolution is **source_id-only indexing**: do not auto-register on fuzzy step 3/4 (`team_identity.py:110:132` `register_team_identity` on fuzzy hit) — require an explicit `source_id` or human-curated alias to enter the mapping table.

### EVIDENCE — code + specimen

`event_registry.py:52` `from name_normalization import names_match`, `:83` “names_match still guards the final decision”, `:110` “never the label”, `:242:320` schedule_derived gate + assertion, `:352:357` both-teams `names_match`; `team_identity.py:8:10` pipeline, `:25:40` scores, `:110:132` auto-registration on fuzzy; `team_binding_invariant.py:18` poisoned index and `utils/team_merge.py:7` “its own slug, ZERO mapping rows” (the bare-location class) and `team_merge.py:270/309` mapping mutation and `team_identity_backfill.py:1` backfill. **Incident corpus:** the pre-042 era created many `provenance:unanchored` rows whose `commence_time` was `now` (gotcha #14) and whose `home_team_name` was a bare location — the merge rails later drained some via `name_and_window` (`admin_events.py:386`/`team_binding_invariant.py` Ruling 048 now forbids `name-and-window absorption with a delete`, `event_merge_invariant.py:12`).

### VERDICT

**suspect**. Stepwise, the **event** path is now sound (label only licenses a find for an anchored claim, never a create or an absorption). The **team** path is not — its index is write-permissive (`auto-register on fuzzy`) and its readers are blind-trust (`exact` on a table that was backfilled from the same names). Ruling 042's work on events did not yet reach teams: `team_identity_mapping` is still the exact-match index that `entity_registry.py:338` and `enrich_markets.py:1162` treat as validated at read time when nothing validates it at write time. The result is event merges may be sound while team merges on the same page silently point at the wrong club.

### THE ONE EXPERIMENT THAT SETTLES IT — census, header-only grep + one SQL, read-only

```bash
# Files that still license a bind/merge on a display label (evidence the migration is incomplete):
grep -R "names_match\|_fuzzy_score\|fuzzy_match\|register_team_identity" backend --include="*.py" | grep -v tests | grep -v __pycache__
# Expected: event_registry.py names_match gated by schedule_derived (sound), team_identity.py fuzzy+register (suspect), admin_teams/team_merge/EnrichMarkets consumers (blind-trust).
grep -R "team_identity_mapping" backend --include="*.py" | grep -v tests
# Expected: 18+ producers/consumers of the same index; no writer validates against source schedule.
```

```sql
-- How many mappings were created via fuzzy auto-registered path (step 3/4) vs exact source_id?
SELECT source, COUNT(*) AS mappings,
       COUNT(*) FILTER (WHERE source_id IS NOT NULL) AS with_source_id,
       COUNT(*) FILTER (WHERE source_id IS NULL) AS label_only_fuzzy_created
FROM team_identity_mapping GROUP BY source ORDER BY label_only_fuzzy_created DESC;
-- Expectation: a long tail of label_only_fuzzy_created on espn/statpal is the pre-042 residue that still exact-matches today.
```

---

## 4. CLOCKS: provider timezone assumptions per namespace (the Eastern-as-UTC StatPal find says at least one namespace lies — audit them all).

### CHOSEN

Each ingest namespace declares, or assumes, a clock. The audit finds **four namespaces, three told truths, one systematically lied, one tells no time at all**:

| Namespace | What it emits | What the code assumes its clock is | What we verified it actually was this week | Cite |
|---|---|---|---|---|
| **ESPN** | `commence_time` per `espn_sync.py` `espn_id → schedule` dereference, timezone-aware UTC (`espn_helpers.py:713` “this ESPN game onto a LATER same-matchup sibling within the 28h” + `_SOURCE_PRIORITY 3`) | America/New_York or venue local → normalized to UTC. ESPN is the **time authority** (highest priority). | Truth — except `espn_id` was observed **shared across two real games** on the same date/same matchup (same `espn_id` on two `events` rows). The provider id is assumed unique, but it collided — see §2. | `event_registry.py:56:63`, `espn_sync.py:834` |
| **Odds API** | `commence_time` per API payload (ISO 8601, UTC) — `external_id` keyed | UTC | Truth (ISO 8601 Zulu with tz). Used as first writer before ESPN arrives. | `app/tasks/odds_api.py`, `models:830` |
| **StatPal** | `fixture.commence_time` / `fixture_id` via `statpal_sync.py` `resolve_team` → `team_identity_mapping` → `find_or_create_event` | The code assumed **UTC** (`statpal_sync.py:161` “not buy absorption. No fixture_id ⇒ create.” has no tz conversion path; `event_registry.py:76` “Wide enough for cross-source date disagreements” was the band-aid). This week: **Eastern-as-UTC** systematics — a StatPal `19:07` Eastern first pitch decoded as `19:07 UTC` is **4h early** (23:07 UTC correct). The namespace lies by a fixed offset. | **Lied** — Eastern stored as if UTC, so every StatPal-origin `commence_time` is `+4/5h` off (EDT/EST). The clock, not the score, was the poison. | `statpal_sync.py:161/187`, `team_binding_invariant.py:75` emitter note, `test_kalshi_linkage_date_guard_1811.py:39` `19:07 Eastern = 23:07 UTC` specimen |
| **Kalshi / Polymarket tickers** | No clock at all — **settlement date** `26JUL11` (Kalshi) / Gamma `event.ticker` (Polymarket) with `gotcha #14` “no real game time on the market” | Settlement *date* treated as `commence_time = now()` fallback (`event_registry.py:72:85` “prediction-market auto-creates that fall back to a batch-shared `now`”). Code tolerates `~28h` drift because there is no time to be right about (`prediction_market_matching.py:171` “legitimately sit up to ~28h off”). | Truth by omission — **no time** is correctly no time, but the fallback `now` collapses 177 same-sport events onto one timestamp, which is what forced `LIMIT 500` and `ORDER BY time-proximity`. | `prediction_market_matching.py:171/320`, `event_registry.py:72:85` |
| **DataGolf / internal** | Not a game clock | n/a | n/a | `repair_apply_plan.py:605` Eastern dates for golf twin-bill note, `event_taxonomy.py:434` `UTC-5 approximation — no pytz` |

Two more clocks not in the table but adjacent: `futures_markets.resolution_date` / `futures_outcomes.is_winner` grading and `futures_odds_snapshots.captured_at` — `calibration_captured_at` is deferred scope on #1012 (METHODOLOGY_AUDIT §1 capture-age), and the weekly `DATE_TRUNC('week', resolution_date)` (`cohort_sweep.py:95`) is UTC-Monday while the app's weekly scoreboard is quoted in ET Monday — see SMALL_ERRORS finding #5 (0.3→1.5pp).

### ALTERNATIVE

Make the StatPal namespace's clock **explicitly Eastern → UTC** at the boundary (one conversion at `statpal_sync.py` where the fixture time is parsed, not at every downstream `find_or_create_event`). Store `commence_time_source_tz` alongside `commence_time` so the invariant `completed_at > commence_time` (`event_merge_invariant.py:12`, `#46`) can be checked in the *source's* local time. For tickers: never synthesize a `commence_time` from `now` — leave it `NULL` and forbid `commence_time` from participating in the window for unanchored ticker claims (ruling 048 already forbids absorption, but the `now` collapse still pollutes the candidate set and the 177-timestamp pathology).

### EVIDENCE — code + specimen

`statpal_sync.py:161/187` (StatPal path, `resolve_team` through poisonable mapping), `team_binding_invariant.py:75` statpal emitter, `espn_helpers.py:713` later-sibling within 28h, `event_taxonomy.py:434` `UTC-5 approximation — no pytz`, `test_kalshi_linkage_date_guard_1811.py:39` `19:07 Eastern = 23:07 UTC` (4h), `prediction_market_matching.py:171` 28h legitimate drift, `event_registry.py:72:85` `now` fallback and collapsed timestamp, `event_merge_invariant.py:12` absorption alive one layer down, `sports.py:616` 6h gate. **Incident corpus:** (a) StatPal Eastern-as-UTC — every StatPal-origin game `commence_time` is `+4/5h` early, so StatPal-as-winner (`statpal 2 > odds_api 1`) propagates the lie until `completed_at` guards it; (b) ticker-vs-event 2,069 drift — the 28h tolerance is settlement vs start, not time vs time; (c) shared `espn_id` — the id itself collides, so the clock's authority (ESPN highest priority) cannot be trusted without id uniqueness.

### VERDICT

**wrong** for the StatPal namespace (the provider's emitted time is systematically not UTC and the code had no conversion), **sound** for ESDN/Odds API, **sound-by-omission** for tickers (no clock correctly yields no clock, but the `now` synthesis is the pathology). Ruling 042/048 does not fix a lying clock — it fixes who may *use* the clock. The StatPal clock lies before the gate is even reached.

### THE ONE EXPERIMENT THAT SETTLES IT — clock census, read-only

```sql
-- Per-namespace clock bias: for events that were touched by ≥2 namespaces with distinct commence_time_source,
-- what is the signed offset between them? A systematic +4/5h on statpal vs odds_api/espn is the Eastern-as-UTC signature.
-- Requires the event history or at least commence_time_source to be present (it is: models Event.commence_time_source).
SELECT commence_time_source,
       COUNT(*) AS events_this_source_won_clock,
       -- Compare against the audit that re-parses StatPal fixture time in the correct tz (one-off dyno, header-only, read-only)
       -- Interim read-only proxy: drift between ticker-linked event time and ticker settlement date
       AVG(EXTRACT(EPOCH FROM (ticker_date - commence_time))/3600) AS avg_ticker_drift_h
FROM events e JOIN futures_markets m ON m.event_id=e.id
WHERE m.source='kalshi' -- or polymarket
GROUP BY commence_time_source;
-- Expectation: statpal-origin rows cluster at +4.0h (EDT) or +5.0h (EST) vs espn/odds_api origin rows; ticker vs event drifts 24–28h tail is settlement, not a clock.
```

---

## 5. THE INDEX LAYER: team_identity_mapping and its siblings — what validates them at write time now, what re-validates at read, and what other blind-trust exact-match indexes exist.

### CHOSEN

The **current validation posture** for indexes is summarized below. There is one index that is exact-match blind-trust (`team_identity_mapping`), one that is exact-match with a gate (`events` via `event_registry.py`), and two that are exact-match on a synthetic key (`futures_markets`/`futures_outcomes`).

| Index (table + key) | Write-time validation today | Read-time revalidation today | Blind-trust consumers | Cite |
|---|---|---|---|---|
| **`team_identity_mapping` `(source, source_id, sport_key) / (source, source_name, sport_key)`** | **None.** Any `(source, source_name)` that fuzzy-matches the teams table is `INSERT`'d via `register_team_identity` on the fuzzy path (`team_identity.py:110:132` `await register_team_identity` on step 3/4 — no schedule check, no provider id check, no human review). The one-time backfill (`team_identity_backfill.py:1`) inserted every distinct alias from existing data — including bare-location names that are *zero-mapping* slivers (`team_merge.py:7` “its own slug, ZERO mapping rows … only a stray event”). | **None.** Every reader does `exact match` on the same key and trusts it: `entity_registry.py:255` “every distinct `team_identity_mapping.source_name` … are read-only here”, `enrich_markets.py:1112/1162` “falls back to `team_identity_mapping`”, `teams.py:47` `source='legacy_slug'` pointing at the target team, `admin_teams.py:100`/`team_merge.py:270` merges via `UPDATE team_identity_mapping`. No reader re-checks the source schedule. | All team-resolution code: `team_identity.py` itself (steps 1–2 are exact on the table, so a prior fuzzy insert now wins as exact), plus `entity_registry`, `enrich_markets`, `teams` route. | `team_identity.py:8:10/110:132`, `team_identity_backfill.py:1`, `team_binding_invariant.py:18`, `team_merge.py:7/270/309`, `entity_registry.py:255/338`, `enrich_markets.py:1112` |
| **`events` `(external_id / espn_id / statpal_fixture_id)` + `(sport_id, commence_time ±28h, names_match)`** | **Validated** — `external_id`/`espn_id`/`statpal_fixture_id` are provider ids, not labels, and Step 1 is exact on the provider's column; Step 3 is gated by `schedule_derived=True` and `names_match` on both teams plus the `#46` `commence_correction_inverts_completion` guard (`:405:424`) and the `ORDER BY time-proximity + LIMIT 500` (`:326:342`). | The only re-validation that ever fires is the **merge** rail (`sports.py:616` 6h separation + `admin_events.py:386/561` dedup), which is downstream and blocked from `name-and-window absorption with a delete` by `event_merge_invariant.py:12` (Ruling 048). There is no read-time schedule re-check on the `events` index otherwise — the row's `espn_id` is trusted on sight. | `_find_by_source_id` itself — it returns the row on `espn_id` equality without re-deriving the schedule. That is how a shared `espn_id` absorbs a second real game without a window or names check (Step 1 needs neither). | `event_registry.py:268:286`, `:242:320`, `:405:424`, `event_merge_invariant.py:12` |
| **`futures_markets.ticker` / `(source, group_id, event_id)` + `futures_outcomes` grouping** | **None beyond the poller.** Polymarket's `group_id = f"polymarket:{event.id}"` for multi-market events (`polymarket.py:group_id`) and Kalshi ticker prefix are trusted as grouping keys; `group_id` reuse across marquee events (the `group_id` reuse class) makes this a de-facto index that binds the *group's* sums histogram (`admin_cohort.py:330` `SUM … per COALESCE(group_id, event_id)`) to the wrong container. | None — the sums histogram trusts `COALESCE(group_id, event_id)` as “group or singleton” without checking `outcome_relation` (`market_shape.py:90`). The calibration audit's histogram split fix (request that it split by `outcome_relation`) is the deferred re-validation. | `precompute_calibration.py:262` “its prices neither sum to ~1.0 …”, `admin_cohort.py:330` group sums, `RELATED_FUTURES dedup_by_merge_group` (`related_futures.py:28`). | `polymarket.py:group_id`, `admin_cohort.py:330`, `market_shape.py:90` |
| **`teams.slug` / `legacy_slug` mapping rows** | One-time `team_identity_backfill` and `team_merge.py:309` `INSERT INTO team_identity_mapping … source='legacy_slug'` — slug is the only validated namespace (unique, immutable). | `teams.py:47` “registered in `team_identity_mapping` (source='legacy_slug') pointing at the merged team's `slug`” — read as exact and trusted, which is correct for slugs. | `teams` route public API — but legacy slugs can still dangle after a merge if not moved (`team_merge.py:270`). | `team_merge.py:25/309`, `teams.py:47` |

The **team** index stands alone as the one that is **write-permissive and read-blind** while also being the *join key* for `statpal_sync → event_registry` — 15 of StatPal's fixtures flow through `team_identity_mapping` (`statpal_sync.py:187` `resolve_team reads team_identity_mapping`), so a poisoned mapping is an event-creation poison: the fixture's `home_team_name` is resolved via the wrong `Team` but still presented as the fixture's teams to the registry — and the registry's `names_match` then matches the *poisoned* names against the candidate slate, which is a second blind trust built on the first.

### ALTERNATIVE

Make `team_identity_mapping` **source_id-gated at write**: only `INSERT` when `source_id` is present and dereferences to the same `(sport_key, source_name)` against the provider's schedule (the same `schedule_derived` predicate that gates event absorption). Label-only fuzzy hits remain **in-memory** and are not persisted — they are recomputed each time (or cached under a separate `fuzzy_alias` namespace that readers do **not** treat as exact). At read time, re-validate the mapping against the provider's current team list (ESPN/StatPal team directory) before exact-matching — the same way the Sentinel re-validates calibration grid freshness.

### EVIDENCE — code + specimen

`team_identity.py:8:10` priority (steps 1–2 are exact on the same table steps 3–4 populate), `:110:132` auto-register on fuzzy (the write-permissive path), `:25:40` `_fuzzy_score` 40–60 containment/mascot; `team_identity_backfill.py:1` one-time insert from legacy names; `team_binding_invariant.py:18` “writer is faithful; the INDEX it reads is poisoned” + `:75` `statpal_sync` is the emitter; `team_merge.py:7/25/96/270/309` bare-location zero-mapping slivers + mapping mutation on merge; `entity_registry.py:255/338` and `enrich_markets.py:1112/1162` blind-trust exact readers; `event_registry.py:15` duplicate-vs-absorption asymmetry and ruling 042/048. **Incident corpus:** shared `espn_id` (index-row collision on `events.espn_id` — write had no uniqueness beyond the single-column unique that was assumed, not enforced across games), ticker-vs-event 2,069 (ticker as grouping index, not event index, so not a team-index incident), StatPal Eastern-as-UTC (clock poison, not team poison — but resolved through the same mapping, so the mapping's false alias can *steady* the clock lie).

### VERDICT

**wrong** for `team_identity_mapping` as currently written and read — it is the only index described as “exact-match” that is populated by a fuzzy matcher and then treated as validated. The event index and market slug indexes are **suspect** (they trust the first writer's `espn_id`/`ticker` without re-derivation, but they are id-based, not label-based, so the blast radius is smaller and rulings 042/048 already bound it with the 6h dedup separation and the unanchored tag).

### THE ONE EXPERIMENT THAT SETTLES IT — index census, read-only

```sql
-- Write-time validation gap: how many mappings were created without a source_id (label-only, i.e., fuzzy path)?
SELECT source, sport_key, COUNT(*) AS mappings,
       COUNT(*) FILTER (WHERE source_id IS NULL) AS label_only,
       COUNT(*) FILTER (WHERE source_abbreviation IS NOT NULL) AS with_abbr
FROM team_identity_mapping GROUP BY source, sport_key ORDER BY label_only DESC;

-- Read-time blind-trust twin: how many events carry a team whose only evidence is a label-only mapping?
-- (Proxy: events whose home Team has ZERO mapping rows with source_id, only source_name aliases)
SELECT sport_id, COUNT(*) AS events_on_label_only_home_team
FROM events e JOIN teams t ON (
  t.name = e.home_team_name OR t.id IN (SELECT team_id FROM team_identity_mapping m WHERE m.source_name=e.home_team_name)
)
WHERE NOT EXISTS (SELECT 1 FROM team_identity_mapping m2 WHERE m2.team_id=t.id AND m2.source_id IS NOT NULL)
GROUP BY sport_id;

-- Sibling index trust: group_id reuse across distinct real marquee events (same group_id, different commence_time)
SELECT group_id, COUNT(DISTINCT event_id) AS events_sharing_group, MIN(commence_time) AS first, MAX(commence_time) AS last
FROM futures_markets WHERE group_id IS NOT NULL GROUP BY group_id HAVING COUNT(DISTINCT event_id) > 1 ORDER BY events_sharing_group DESC LIMIT 20;
-- Expectation: any group_id shared across events >24h apart is the group-reuse class — the market slug index is reusing a container.

-- Events index uniqueness: shared espn_id specimen — is espn_id unique?
SELECT espn_id, COUNT(*) AS c, array_agg(id) AS event_ids, array_agg(commence_time) AS times
FROM events WHERE espn_id IS NOT NULL GROUP BY espn_id HAVING COUNT(*) > 1;
-- Expectation: 0 is correct; any row is the shared-espn_id incident (write-time uniqueness not enforced beyond the single-column unique the code assumed).
```

---

## Cross-incident synthesis — each specimen EXPLAINED by which assumption

| Specimen (this week) | Which § explains it | Why the mapping is exact |
|---|---|---|
| **StatPal Eastern-as-UTC** (systematic `+4h`) | §4 Clocks (wrong) + §5 Index | The clock that lied was the one the mapping delivered (`statpal_sync` → `resolve_team` → `event_registry` names). The index did not cause the lie, but it delivered the lie's teams to the registry without re-validating the schedule. Fix §4 (convert at the boundary) drains the specimen even if §5 stays poisoned; fix §5 alone does not — the clock still lies. |
| **Shared `espn_id` across two real games** | §2 ID precedence + §5 Index | Step 1 `espn_id` exact absorbs without any window or names check (`event_registry.py:276:284`). The event index trusts `espn_id` as unique; the provider emitted a collision (or the row was manually mutated). The downstream 6h dedup (`sports.py:616`) is the only separation, but it runs *after* the absorption. Explainable as “first-writer `espn_id` wins, no schedule re-derivation on read.” Fix §2/§5 (write-time uniqueness + read-time schedule re-check on `espn_id`). |
| **2,069 ticker-vs-event date disagreements** | §1 Windows + §2 Ticker precedence | Ticker's calendar date is **settlement**, not start (`prediction_market_matching.py:171` ~28h). The 28h window tolerates the drift, so the specimen is not a *missed* match — it is a *tolerated* date divergence where no path records who is authority for time. Fix §2 (ticker never wins a time fight). |
| **Eponymous-team cross-league aliases** (Panthers etc.) | §3 Name matching + §5 Index | Fuzzy `_fuzzy_score` mascot/last-word 40 + containment 60 plus auto-registration means a “Carolina Panthers” row created in NFL can be exact-matched by a later NHL “Panthers” label as `source_name` exact. The mapping table has no `league`/`sport_key` discriminator beyond `sport_key`, and `sport_key` was `100% NULL` at census (`market_shape.py:3:8`). Fix §3/§5 (do not auto-register on fuzzy; require `source_id`). |
| **177-event collapsed-timestamp slate 2026-07-13** | §1 Windows | `prediction_market_matching.py:now` fallback collapsed every same-day, same-sport auto-create onto one timestamp, so the ±28h window held a full day's slate and `LIMIT 30` truncated the true sibling. The specimen is a pathology, not a schedule — fix is at the write side (`now` → `NULL`), not the window. The cap is now 500 + `ORDER BY time-proximity`, which papers over the pathology. |
| **Any future incident where two same-matchup, same-date rows remain separate** | Already explained — Ruling 048 duplicates go up by design. A duplicate that survives is not an incident unless the id finally arrived and reconciliation did not drain it. | The `provenance:unanchored` tag (`event_registry.py:93/183`) makes the duplicate countable; the duplicate meter's expectation is the gate experiment for this class, not the absence of duplicates. |

*Any incident **not** in this table that still occurs after §5 and §4 are fixed is a finding: it means either a new provider namespace was added without a clock declaration, or a new index was added that exact-matches on a label-derived key.*

---

## Top-5 highest-impact (post-§, fixes gated by the experiments above)

Ranked by expected incident-rate impact (how many future events the wrong assumption will misjoin or duplicate):

1. **Index layer blind trust — `team_identity_mapping` fuzzy auto-registration** — wrong. `team_identity.py:110:132` + `backfill.py:1`. Every new fuzzy hit becomes a future exact; the StatPal emitter (`statpal_sync.py:187` 15-fixture class) and the entity registry read it blind. Incident rate: every cross-league eponymous alias + every bare-location sliver auto-registers once and then survives as exact. *Experiment:* label-only mapping census SQL above (`source_id IS NULL` count) gates the fix (require `source_id` or human alias to enter the table).

2. **Clocks — StatPal Eastern-as-UTC + ticker date-as-time** — wrong for one namespace, wrong-by-omission for one. `statpal_sync.py:161`, `prediction_market_matching.py:171`. Every StatPal-origin game is `+4/5h` early until `completed_at`; every Kalshi market that falls back to `now` collapses the candidate set. Incident rate: 100% of StatPal fixtures, 100% of `now`-fallback markets. *Experiment:* clock bias `AVG(epoch drift) ~4.0h` census above gates the Eastern→UTC conversion.

3. **ID precedence — four tables, four winners** — suspect. `event_registry.py:56:63/268:386` vs `team_identity.py:8:10` vs `prediction_market_matching.py` linker vs ticker. Incident rate: every shared `espn_id` collision joins the wrong two games without a window/names check; every ticker-vs-event 24–28h drift is adjudicated by no table. *Experiment:* precedence matrix `multi` CTE + ticker-vs-event `ABS(epoch drift)` tail census gates the single-table fix (time authority ≠ sport priority, ticker never wins time).

4. **Name matching — residual label-trusting binds beyond the gated `names_match`** — suspect. `team_identity.py:_fuzzy_score 40/60` + `entity_registry.py:255` blind-trust read. Ruling 048 made *event* name use gated, but *team* name use is not — a team label still creates a mapping that later event names trust. Incident rate: every new team name with a common mascot or city substring has a `60/40` chance to auto-register the wrong club on first sight. *Experiment:* `register_team_identity` on fuzzy census grep above gates the “do not auto-register on fuzzy” fix.

5. **Time windows — ±28h candidate filter + 6h anti-absorption, derived from the wrong distribution** — suspect. `event_registry.py:67/326/72` + `sports.py:616`. The 28h is ticker slop, not schedule closeness; 6h is asserted, not measured from `LEAD(commence_time)` on real schedule. Incident rate: doubleheaders `5–6h` and consecutive-day series `~18h` sit precisely on the 6h boundary; any future league with a shorter turnaround (e.g., Olympic basketball 4h) would be absorbed. *Experiment:* real-schedule `LEAD(commence_time)` `p1 <6h` distribution and ticker-drift `24–28h` tail census above gate the two-window design (`±6h` for clocked sources, `±28h` only for date-only ligatures).

---

## What “no fixes” still ships with each row

The calibration audit's “re-baseline” section had a before/after protocol. For matching, the analogue is an **incident-meter re-run** — each row's gate experiment is also its proof:

* Before: snapshot the census before the fix (`before.json` — the row's COUNTs / drift histogram / `label_only` tallies).
* After one row lands, re-run the same header-only census.
* Required movement (from table): `team_identity: label_only count → 0` for new rows; `clocks: StatPal bias 4.0h → 0.0h`; `id precedence: shared espn_id count → 0`; `name matching: fuzzy auto-registered mappings drop to 0 new`; `windows: p1 <6h pairs not absorbed, 177-collapsed timestamp class → 0`.

A matching fix that does not move its census is not “fixed and not declared” — it is not fixed.

---

## Provenance

Method citations are the code; numbers are from the light API where the 200k/300k random sample (`ORDER BY random()` added `a6665b14`) allows and from the incident record (2,069 ticker drifts, 177-event collapse, shared espn_id). The 6h vs 28h constants and their distribution experiment are this audit's contribution; the schedule-derived vs label-parsed distinction is the standing work of rulings 042/048.

