# The tournament register

The grid-register pattern (ratified 2026-07-31) carried to tournaments whose unit is a **player in
a draw** rather than a team in a stage. The US Open is the first, shipping for main-draw Sunday
2026-08-30.

**The contract:** the page reads the register and nothing else. A market not in the register does
not render. Identity is decided once, by an agent, in a committed file — never by fuzzy matching
at request time.

---

## Where it lives

| thing | path |
|---|---|
| Schema, validators, drift + freshness checks, lookup view | `backend/app/utils/tournament_register.py` |
| Committed register (the data) | `backend/data/tournament_registers/us-open-2026.json` |
| Generator (how the agent maintains it) | `backend/scripts/generate_tournament_register.py` |
| Guard tests | `backend/tests/test_tournament_register.py` |
| The census it was built from | `docs/us-open-2026-market-census.md` |

Naming is `<tournament>-<season>.json`, resolved by `load_register(tournament, season)`. A missing
or unreadable file returns `None`, which renders an honest empty page — **a broken register
degrades to nothing, never to a wrong number.**

## Why a second module rather than widening `grid_register`

The grid's cell is `(stage, entity, source)` and its entity identity is anchored on the `teams`
table. A tennis draw has no teams table to anchor to; its rows carry draw / seed / draw-slot state
a grid cell has no place for; and its daily slate is a *pair* of registered players sharing one
market. The shape forks — but the **vocabulary is imported** (`REGISTER_STATUSES`,
`TERMINAL_RESULTS`, `_HARD_INVALID_PREFIXES`, `is_iso8601`, the `classify` ordering), so both
registers say the same words about the same situations. That is the part that must not drift.

Nothing here is wired into the shipped grid path.

---

## Shape

```jsonc
{
  "schema_version": "tournament-register/v1",
  "tournament": "us-open", "season": "2026",
  "version": 1, "generated_at": "2026-08-25T00:50:00+00:00",
  "draw_released": false,            // a LATCH: false -> true only, never back
  "players": [{
    "entity_key": "felix-auger-aliassime",   // pinned once; survives source renames
    "display_name": "Felix Auger-Aliassime",
    "draw": "mens-singles",                  // register-owned; llm_gender is NULL on all rows
    "seed": null, "country": null,
    "draw_slot": null, "section": null,      // empty until the ceremony, and ENFORCED so
    "sources": [{
      "source": "kalshi",
      "market_id": 34277822, "outcome_id": 152600804,
      "market_external_id": "KXATP-26USO", "outcome_external_id": "KXATP-26USO-AUG",
      "source_name": "Felix Auger-Aliassime",   // what THIS source calls them
      "status": "live",                          // live | settled | missing
      "terminal_result": null,                   // won | eliminated, when settled
      "price_observed_at": "2026-08-17T09:00:00+00:00",
      "evidence": {"kind": "outright-field-census", "observed_at": "..."}
    }]
  }],
  "matchups": [{                     // the daily slate; empty at v1
    "matchup_key": "...", "draw": "...", "round": "R128",
    "scheduled_date": "2026-08-31",
    "players": ["entity-a", "entity-b"],       // must BOTH already be registered
    "sources": [{"source": "polymarket", "market_id": 1, "status": "live",
                 "evidence": {},
                 "sides": {"entity-a": {"outcome_id": 11},
                           "entity-b": {"outcome_id": 12}}}]
  }]
}
```

`sides` is the load-bearing field for the slate. The census found match-market outcome names are a
mix of `Yes`, `No`, and the repeated market title — mapping `entity_key → outcome_id` explicitly is
what makes the slate print player names instead of "Yes 54% / No 47%".

### Rules the validator enforces

| finding | what it stops |
|---|---|
| `INVALID_NON_PLAYER_ENTITY` | the `Other` bucket pinned at 100% leading both boards |
| `INVALID_DRAW_SLOT_BEFORE_RELEASE` | a draw slot guessed before the ceremony, wearing the authority of a fact |
| `INVALID_DRAW_RELEASED_UNLATCH` | un-latching `draw_released`, which would un-validate every committed slot |
| `DUPLICATE_PLAYER_ACROSS_KEYS` / `IDENTITY_REUSED_ACROSS_PLAYERS` | one player as two rows, or one market feeding two players |
| `MATCHUP_PLAYER_NOT_REGISTERED` / `MATCHUP_NOT_A_PAIR` | a stale Cincinnati market becoming a slate row |
| `LIVE_PRICE_STALE` / `LIVE_PRICE_NEVER_OBSERVED` | month-old prices presented as today's |
| `UNREGISTERED_RENDER_ROW` | *a market not in the register does not render* — enforced at the render boundary, not just documented |

`classify()` maps findings to `(classification, action, publish)` in strict severity order:
**invalid → needs_ruling → render_contract_failure → unambiguous_drift → clean**. Structural
severity is decided by an explicit `STRUCTURAL_FINDINGS` set as well as name prefixes, because
prefix-matching is a naming convention doing a classifier's job — the same hole is live in
`grid_register` today (#2198).

---

## How the daily drift sentinel checks it

Runs daily, mirroring `tasks/grid_register_sentinel.py`. It never edits the register; it either
proposes a new version or files an issue.

1. **Load and validate.** `load_register` → `validate_register`. Any finding whose classification
   is `invalid` is a **hard stop**: file P1, propose nothing. A register we cannot trust must not
   be used to judge whether the world changed.
2. **Build the inventory** — the live `(source, market_id, outcome_id, outcome_name, status,
   terminal_result, season)` rows for the market ids the register pins. Load is bounded by
   `TournamentRegister.market_ids()`, so the sentinel queries four markets, not the 861,809-row
   table. **The generator and the sentinel must share one inventory implementation** — this is the
   grid register's hardest-won lesson: two implementations report phantom drift against each other
   forever.
3. **Diff** — `diff_against_inventory`. The asymmetry is deliberate:
   - a **rename** that keeps the pinned identity → `UNAMBIGUOUS_RENAME_DRIFT`, auto-versionable
   - a **settlement** carrying a result → `UNAMBIGUOUS_SETTLEMENT_DRIFT`, auto-versionable
   - settled with **no** knowable result → `SETTLEMENT_WITHOUT_RESULT` → a human
   - identity **vanished** or **two candidates** → a human, always
   - Punctuation/space churn is normalised away first, so the sentinel does not wake every night
     over `Auger-Aliassime` vs `Auger Aliassime`.
4. **Check freshness** — `check_freshness`, reading `price_observed_at` (sourced from
   `futures_odds_snapshots.captured_at`, *never* `futures_outcomes.last_updated`, which the census
   proved reads a month stale). Past `STALE_PRICE_HOURS = 6`, the row is blocked from rendering as
   a live number.
5. **Check the render contract** — `check_rendered_rows` against what the page would actually
   emit. This is the direction that catches leaks: a row the register does not carry is
   `UNREGISTERED_RENDER_ROW`.
6. **Classify and act.** `auto_version` → build the proposed register, run `validate_transition`
   (monotonic version, same scope, `supersedes_version` link, latch respected), publish only if it
   validates. `file_issue` → one deduped P2 with a drift fingerprint and three concrete options.
   `clean` → record the check and change nothing.

**Not yet wired to Celery beat.** The task is registered on the day the register writer ships, so
this queue leaves `beat_schedule_change: false` and does not touch the
`tests/test_tasks_wiring.py` allowlist. The pure functions above are shipped and tested now; the
sentinel's daily cadence is Day 2+ work, because a sentinel cannot usefully guard a register no
page reads yet.

---

## Maintaining it

```bash
cd backend && python3 scripts/generate_tournament_register.py \
  --tournament us-open --season 2026 \
  --field mens-singles=kalshi:/tmp/uso/KXATP-26USO.json \
  --field mens-singles=polymarket:/tmp/uso/139236.json \
  --field womens-singles=kalshi:/tmp/uso/KXWTA-26USO.json \
  --field womens-singles=polymarket:/tmp/uso/139255.json \
  --freshness /tmp/uso/freshness.json \
  --observed-at 2026-08-25T00:50:00+00:00 \
  --out data/tournament_registers/us-open-2026.json
```

The generator **refuses to write a register that does not validate**, and its docstring carries
the exact census SQL so the input is reproducible without archaeology.

### The second population pass — contenders are not participants (v2, UX-P132)

v1 was seeded from the outright fields: 80 **contenders**, correct for the boards. The slate's
players are the qualifying draw, and most are not contenders, so `MATCHUP_PLAYER_NOT_REGISTERED`
rejected every qualifying matchup — correctly and loudly. v2 closes that by registering the
participants too, and the fix is a new field rather than a loosened rule.

```bash
# 1. dump the condition markets (the Yes/No rows) from production
#    — the exact SQL is in fetch_usopen_match_census.py's docstring
# 2. join them to the source's own side labels and real schedule
cd backend && python3 scripts/fetch_usopen_match_census.py \
  --db-dump /tmp/uso/cond_outcomes.json \
  --observed-at 2026-08-25T21:30:00+00:00 \
  --out /tmp/uso/match-census.json

# 3. supersede the committed register with the second pass applied
python3 scripts/generate_tournament_register.py \
  --tournament us-open --season 2026 \
  --base data/tournament_registers/us-open-2026.json \
  --matchups /tmp/uso/match-census.json \
  --exclude /tmp/uso/stale-open.json \
  --observed-at 2026-08-25T21:30:00+00:00 \
  --version 2 --supersedes-version 1 \
  --out data/tournament_registers/us-open-2026.json
```

`--base` carries the previous version's players forward **verbatim**. A register version
supersedes its predecessor; it does not re-decide it. Re-deriving identity from fresh dumps every
run would mean a source renaming a player silently re-slugs their `entity_key` — precisely what a
pinned identity exists to survive.

| field | values | what it decides |
|---|---|---|
| `player.role` | `contender` \| `participant` (absent ⇒ `contender`) | whether the player is a **championship-board row**. Participants have no player-level source and are invisible to `build_boards` by construction |
| `source.kind` | `outright` \| `match` (absent ⇒ `outright`) | which *question* the pinned identity answers. `INVALID_MATCH_SOURCE_ON_PLAYER` stops P(wins this match) from being blended into P(wins the tournament) |

Without the role split, populating the slate would have put a first-round qualifier on the men's
championship board above Alcaraz, priced from a qualifying quote. That is not a wrong number so
much as an answer to a different question — which is worse, because it looks entirely plausible.

`TournamentRegister.board_players()` is the contender-only view; `draw_players()` still returns
everyone. Boards read the former.

### Where the sides mapping comes from — read, not parsed

`sides` maps `entity_key → outcome_id`, and it is the reason the slate prints player names instead
of `Yes 54% / No 47%`.

**Nothing in our own database says which player `Yes` means.** Measured 2026-08-25:
`futures_outcomes` has no column carrying the source's outcome label, and
`market_metadata->'shape'` records `side_kind: "yes_no"` — a *kind*, never a *which*. The repo's
only Yes-to-competitor rule is a market-**name** parse (`prediction_market_matching.MatchupInfo`,
always the first-named side) that ships with an inversion backstop precisely because it is
unreliable. Doctrine clause 4: label equality is not identity.

So the mapping is read from Polymarket Gamma's `moneyline` sub-market, which states it outright —
`outcomes: ["Andrea Guerrieri", "August Holmgren"]`, ordered, and our write contract pins `_yes`
to `outcomes[0]`. The fetcher **verifies that ordering against each match's own title and drops
any match where they disagree** rather than guessing; at the measured moment 162/162 agreed and 0
were rejected. The labels are then pinned into `evidence.source_labels`, so the mapping stays
checkable later without re-fetching.

This is the register doctrine paying out: an identity decision made once, offline, from the best
available evidence, is better than a request-time parse that is known to invert.

### The stale-open slot

Three independent gates keep a finished match off the slate, and a match is dropped if any fires.
The generator prints a named count for every drop — a short slate must always have an answer,
because a silent exclusion reads as an absence.

| gate | catches | measured 2026-08-25 |
|---|---|---|
| `SOURCE_CLOSED` | the source says the match is over | **95 of 162** |
| `START_TIME_PAST` | started more than 6h ago and the source has not flagged it yet | **1** |
| `MANUALLY_EXCLUDED` | `--exclude`, a JSON list of event ids — the slot for the measurement lane's stale-open inventory | 0 (none staged) |

The third exists because the first two cannot see everything: gotcha #33's Kalshi Cincinnati set
is graded-but-`open` with no source-side `closed` flag to read. It is a file so the list can be
updated without a code change.

**Our own columns cannot do this job.** At the measured moment all 324 US Open qualification rows
read `status='open'` with `resolution_date` 08-31/09-02, while the source reported real dates of
08-24/25/26. A date-window slate keyed on `resolution_date` would have shown 64 finished Monday
matches as Sunday's card — gotcha #33 at 59% of the population, and gotcha #14 (a resolution date
is a close time, not a start).

`tournament_slate.build_slate` re-applies the same 6h bound at serve time. The register is a
committed file; the clock is not.

---

## Alex's mock verdict — the re-skin (2026-08-25, UX-P132)

Taste rulings, applied as a re-skin and never a restructure. Reference screenshot:
`.claude/handoff/_KALSHI-REFERENCE-baseball-champion.png`.

| # | ruling | where it lives |
|---|---|---|
| 1 | C is the base, but take A's **men's/women's pill everywhere** — never two stacked gender lists — and B's ordering: **today's matches lead the page** | `app/tournaments/[slug]/page.tsx` |
| 2 | **Legend of the top 3 → three-line chart → collapsed list**, endpoint dots, timeframe selector bottom-right | `components/tournament/ContenderChart.tsx`, `lib/contenderChart.ts` |
| 3 | **Collapse to 3 rows + "Show all N"** — Alex's P1, and his own reference settled 3-vs-5 | `components/tournament/TournamentBoard.tsx` |
| 4 | **Where to watch** — a static per-tournament mapping is an acceptable v1 | register `broadcasts`, `lib/slate.ts` `broadcastFor` |
| 5 | **Curated props & futures** — interestingness bar, not a dump | register `props`, `scripts/populate_tournament_props.py` |
| 6 | **Bracket mocked with dummy data now**, ahead of the ceremony | `docs/mocks/us-open/us-open-reskin.html` |

### Adaptation, not imitation

The reference's contender rows carry **two-sided green/red price pills** (`34.5%` / `65.5%`).
That is a trading format, and copying it would breach the standing no-price-format ruling. Our
rows print **one blended probability** per contender. What was taken is the *structure* —
legend → three-line chart → collapsed list — and the colour tie-in, where a charted contender's
name is underlined in its own line colour.

`__tests__/components/tournamentReskin.test.tsx` asserts the refusal directly: every row emits
exactly one `row-probability`, and a board showing `34.5%` must not also render `65.5%`.

### Standing doctrine the chart does not get to bend

- **Fixed 0-100 axis.** `chartGeometry` never scales to the data range. Asserted: two points at
  0.50 and 0.52 plot at y=50 and y=48 on a 100-high box, not at the top and bottom.
- **No smoothing, no interpolation.** Straight segments between real observations; an unobserved
  day is a gap, not a filled point.
- **One shared x-domain** across the three lines, so a late starter begins part-way across
  instead of being stretched to fill the width. Per-series x-scales would put Monday under
  Thursday and make a crossing meaningless.
- **A timeframe is measured back from the LAST OBSERVATION, not from `now`.** With the fields
  price-dark 8–32 days, a window anchored on today would be empty for a market holding a full
  month of history that ended three weeks ago — the chart would read "no data" when the truth is
  "no *recent* data", which the banner already states properly in words. An undrawable window is
  offered **disabled** rather than blank.
