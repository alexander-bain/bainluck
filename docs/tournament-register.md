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

### Known gap — contenders are not participants

v1 is seeded from the outright fields: 80 contenders, correct for the boards. The slate's players
are the qualifying draw, and most are not contenders, so `MATCHUP_PLAYER_NOT_REGISTERED` would
reject every qualifying matchup today — correctly and loudly. **Day 3 must add a second population
pass over the match markets before any matchup is added.** See census §5.
