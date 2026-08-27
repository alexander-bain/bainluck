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

### `reaches` — the playoff grid's cell (UX-P139)

Alex's amendment to ruling 3: *"a blank cell, an improperly blended cell, or a cell populated from
the WRONG future is a linkage defect — no excuse, no interpolation ... The register carries
per-player per-round market IDs from BOTH sources; the grid reads only the register."*

```jsonc
"reaches": [{
  "draw": "mens-singles",
  "entity_key": "carlos-alcaraz",
  "round": "SF",                       // one of ROUNDS
  "sources": [{
    "source": "polymarket", "kind": "reach",
    "market_id": 59556735, "outcome_id": 221650932,
    "market_external_id": "0x0d62…", "outcome_external_id": "0x0d62…_yes",
    "source_name": "Yes",
    // THE THREE RESTATEMENTS. Validation asserts each against the cell, so a
    // reach-QF market wired into the SF cell REFUSES THE REGISTER rather than
    // rendering a plausible number in the wrong column.
    "question_round": "SF", "question_draw": "mens-singles",
    "question_subject": "Carlos Alcaraz",
    "question": "Will Carlos Alcaraz advance to the Semifinals in Men's Singles at the 2026 US Open?",
    "status": "live", "price_observed_at": "…",
    "evidence": {"kind": "advance-ladder-census", "observed_at": "…", "polymarket_event_id": "910171"}
  }, {
    // A CENSUSED ABSENCE, not an omission. Both sources get a block; the one
    // that carries nothing says so, with the date we looked.
    "source": "kalshi", "kind": "reach", "market_id": null, "outcome_id": null,
    "status": "missing",
    "evidence": {"kind": "advance-ladder-census-absent", "observed_at": "…", "note": "…"}
  }]
}]
```

| finding | the failure it names |
|---|---|
| `REACH_ROUND_MISMATCH` / `REACH_DRAW_MISMATCH` / `REACH_SUBJECT_MISMATCH` | **wrong-future placement** — a real price, from a real market, under the wrong question |
| `DUPLICATE_REACH_CELL` / `REACH_IDENTITY_REUSED` | two markets for one cell, or one quote printed under two questions |
| `REACH_SOURCE_WRONG_KIND` | P(wins the title) rendered in the "reaches the semis" column |
| `REACH_PLAYER_NOT_REGISTERED` / `REACH_PLAYER_WRONG_DRAW` | a cell for somebody the register does not carry |
| `REACH_NO_SOURCES` / `REACH_BLOCK_MISSING_QUESTION` | a cell nobody censused, or a block that cannot be checked |

All of them are `STRUCTURAL_FINDINGS`: the register is **rejected**, not served with a warning.

**The census behind it (2026-08-26).** Kalshi publishes **zero** round-advancement futures for this
tournament — its whole US Open inventory is five markets. Polymarket publishes **336**, in eight
`To Reach {R16, QF, SF, Final} × {Men's, Women's}` events, covering 44 of 128 men and 40 of 128
women; verified against Gamma directly, so that is their inventory and not an ingest shortfall.
Within it, coverage is total: all 84 players carry all four rounds, so **no player has a
quarter-final number, a title number and a blank between them.** 28 board contenders have no
ladder at either source; their cells are `no_market`, which is a census result and not an alarm.

**Freshness.** `refresh_registered_tournament_prices` (every 10 min, `background`) asks Gamma for
exactly the condition ids pinned here — `/markets?condition_ids=…`, which does not paginate and is
therefore not subject to the offset-2000 cap that leaves the scanning poll reaching a given event
about once a day. Prices only; it never creates a market and never touches identity.

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

## DRAW CEREMONY RUNBOOK — the exact sequence for the day (UX-P136)

**Read this once before the ceremony, then execute it.** Every command below was run end to end
on 2026-08-26 against the synthetic 128-slot draw, and the outputs quoted are the real ones. Draw
day is four steps: **ingest → latch → swap → publish**. They are not four decisions; the latch and
the slots are written by the same command precisely so nobody has to sequence them under time
pressure.

**Starting state, measured 2026-08-26:** register `version: 4`, `supersedes_version: 3`,
`draw_released: false`, 211 players (96 men / 115 women).

**The one thing that will look alarming and is expected:** the register holds 96 men and 115 women
against 128 slots a side, so **45 drawn names have no registered identity**. That is not a bug and
no regeneration pass can fix it — the register is built from *markets*, and nobody quotes a
qualifier who has not qualified yet. `--register-from-draw` is the sanctioned answer and step 1
requires it. Without that flag the script refuses on all 45 and writes nothing.

### Step 1 — Ingest the draw, DRY, and read the admitted list

Save the draw as `{"mens-singles": [{"slot": 1, "name": "...", "seed": 1}, ...], "womens-singles": [...]}`,
128 entries per side.

```bash
cd backend && python3 scripts/ingest_tournament_draw.py \
  --register data/tournament_registers/us-open-2026.json \
  --draw /tmp/usopen-draw-2026.json \
  --version 5 --supersedes-version 4 --register-from-draw \
  --out /tmp/proposed-v5.json
```

`--out` is what makes this dry: it writes a candidate elsewhere and leaves the committed register
untouched. **Verification — all four lines, or stop:**

```
draw_released: False -> True
players with a draw slot: 256
  mens-singles: 128/128
  womens-singles: 128/128
...
findings:   none
transition: clean
```

- `128/128` on **both** sides. A short side means the draw file is short, and `buildBracket`
  refuses a non-power-of-two rather than truncating — you would ship an empty tab with no
  explanation, which is worse than a late one.
- `findings: none` and `transition: clean`. The script refuses to write on either, so a
  non-empty value here is a stop, not a warning.
- **Read the `ADMITTED FROM THE DRAW (n)` list by name.** It is itemised rather than counted for
  exactly this moment. Each admitted row is `role: participant`, `sources: []`, `draw-ceremony`
  provenance — a name and a slot, no market, so no number can render for them anywhere.
- Exit code must be `0`. `1` means it refused; nothing was written and the register is intact.

### Step 2 — Write it in place (this IS the latch)

Re-run the identical command **without `--out`**:

```bash
cd backend && python3 scripts/ingest_tournament_draw.py \
  --register data/tournament_registers/us-open-2026.json \
  --draw /tmp/usopen-draw-2026.json \
  --version 5 --supersedes-version 4 --register-from-draw
```

There is no separate latch step and there must not be one. `draw_slot` is rejected by
`validate_player` while `draw_released` is false — before the ceremony a slot is a guess wearing
the authority of a fact — so the slots and the latch have to land in the **same version**. This
script is the only thing that writes both.

**Verification:**

```bash
python3 -c "import json; d=json.load(open('data/tournament_registers/us-open-2026.json')); \
print(d['version'], d['supersedes_version'], d['draw_released'], \
sum(1 for p in d['players'] if p.get('draw_slot') is not None))"
# expect: 5 4 True 256
```

### Step 3 — The fixture swap. There is nothing to swap.

**This step is a verification only, and that is the whole design.** The bracket has been built
against a synthetic fixture since Day 3, but the fixture was never wired into the page — it lives
under `frontend/__tests__/fixtures/`, which the Next.js app tree does not compile, so it cannot
reach a production bundle. The page has always read `data.bracket[draw]` from the API, which reads
`build_bracket`, which returns `[]` until the latch. **The ceremony is a data change, not a
deploy.** Confirm the swap happened by confirming the same code returns something different:

```bash
cd backend && python3 -c "
import json, sys; sys.path.insert(0,'.')
from app.utils.tournament_slate import build_bracket
reg = json.load(open('data/tournament_registers/us-open-2026.json'))
for d in ('mens-singles','womens-singles'):
    s = build_bracket(reg, prices={}, draw=d)
    print(d, 'len', len(s), 'filled', sum(1 for x in s if x), 'holes', sum(1 for x in s if not x))
"
# expect: len 128, filled 128, holes 0 — on BOTH draws
```

Measured on the rehearsal: `mens-singles len=128 filled=128 holes=0`, same for the women's.
Pre-latch the same call returns `[]`.

**A `holes` count above zero is not fatal but must be understood before publishing.** A hole is a
slot the register holds no player for; the frontend renders it as an undetermined slot and — since
UX-P136 — **never advances the opponent past it as a bye**. With `--register-from-draw` in step 1
there should be no holes at all, so any hole means a draw-file entry the script could not use.

### Step 4 — Publish and verify on the page

Commit the register (it is a committed file, so this is an ordinary deploy of data) and hand it to
the Integrator like any other branch — **this lane does not push.** After it lands:

```bash
source ~/.claude/.env && curl -s "$BAINLUCK_API/api/tournaments/us-open" \
  | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('draw_released', d['draw_released'])
for k,v in (d.get('bracket') or {}).items():
    print(k, 'len', len(v), 'filled', sum(1 for x in v if x))
"
# expect: draw_released True, and 128/128 on both draws
```

Then open `/tournaments/us-open` → **Bracket** tab. What correct looks like:

- The tab opens on the **Round of 128** with 64 match cards, two names each and **no winners** —
  the draw is out, nothing has been played. A winner showing here on ceremony day is a bug.
- The round strip shows all seven rounds; R64 onward say *"Nobody has reached the … yet"* rather
  than rendering rows of empty cards.
- Most names carry **no probability**. That is correct: a 128 field is mostly unpriced, and an
  admitted-from-the-draw player has `sources: []` and can never carry a number.
- The **Tournament** tab is unchanged. The bracket has its own tab specifically so it can never
  displace the boards — the charter's safety property, and the reason a janky bracket is
  survivable on the marquee weekend.

### If it goes wrong

`git revert` the register commit. The latch is a field in a committed JSON file, so rollback is a
file rollback and the bracket returns to "Draw not released" — the boards and the slate are not
touched by any of this, because `build_bracket` is the only consumer of `draw_slot`.

**Never hand-edit `draw_released` to true.** It would pass a naive read and fail
`validate_player` on every slot, and the failure surfaces as an empty bracket with no explanation.

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
