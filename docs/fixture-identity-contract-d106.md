# The fixture identity + lifecycle contract (D106)

**Pillar: TRUTH. Ship: one game is one row, and the row can say which game it is.**
A reader should never see two cards for one fixture, never see a fixture missing, and never
see a kickoff time nobody published. Today the payload a client receives cannot distinguish
any of those cases from a correct one, because it carries no identity beyond two team names
and a timestamp.

Written by `authority/090`, Wed 2026-09-09, under Fable-5's D106 release note (3:32pm PT).
Successor to #2693 (durable matching) and #3840 (fabricated kickoffs). Binds `lane1`,
`live` and `native`; authored by the authority lane, which owns `services/statpal_api.py`,
the shadow anchor stamping and the per-sport authority config (D50) and hands registry
changes to lane1 rather than making them.

**Every number in this document was measured against the venue's own API or production on
2026-09-09.** Nothing here is inferred from our mirror (notice 26). Re-measure before
citing any of it after 2026-10-09.

---

## 1. The captured fixture

`events.id = 14780138` — **New England Patriots @ Seattle Seahawks, 2026-09-10 00:20Z**,
tonight's NFL opener. This is D106's ship-1 specimen and it is currently CLEAN: one row on
both a name query and a whole-window query, so no twin and no container.

| field | value | where it lives |
|---|---|---|
| `id` | `14780138` | `events.id` |
| Odds API id | `8c94552d022acec4a0458d70c19d3da9` | `events.external_id` |
| ESPN id | `401872656` | `events.espn_id` (partial-unique, #2693) |
| StatPal id | `280445` | `events.statpal_fixture_id` |
| StatPal anchor | `statpal / americanfootball_nfl:280445 / game` | `event_provider_anchors` |
| competition + round | `Regular Season / Week 1` | **`event_provider_anchors.claim_context->>'round'` only** |
| season | *nowhere* | — |
| participants | `Seattle Seahawks`, `New England Patriots` (+ team ids 12, 11) | `events.home/away_team_*` |
| start | `2026-09-10 00:20:00+00` | `events.commence_time` |
| start provenance | `espn` | `events.commence_time_source` |
| game number | *not applicable to the NFL* | — |
| lifecycle | `scheduled` | `events.status` |
| created | `2026-05-15` — four months before kickoff | `events.created_at` |

The row is honest, and **the client cannot see almost any of it.** `GET /api/events/14780138`
serves `id, external_id, sport, sport_name, home_team, away_team, commence_time, status,
completed_at, espn.espn_id, metadata.{gender,level,league,importance}, event_tags` — and
nothing else on this table. No StatPal id, no anchor list, no start provenance, no
competition, no season, no round, no game number.

---

## 2. What the venue actually serves — measured 2026-09-09

Read straight off StatPal's own `season-schedule` for every sport we shadow-stamp.

| sport | n | provider id unique | competition | season | round / week | second id (`stats_id`) |
|---|---|---|---|---|---|---|
| NFL | 374 | **no — 6 ids over 52 rows** | 100% (`USA: NFL`) | **0%** | 100% (`Regular Season / Week 1`) | not served |
| NBA | 1208 | yes (1208/1208) | 100% (`NBA`) | 100% (`2026/2027`) | 0% | not served |
| NHL | 1405 | yes (1405/1405) | 100% (`NHL`) | 100% (`2026/2027`) | 0% | 1405/1405 |
| MLB | 182 | yes (182/182) | 100% (`MLB`) | 100% (`2026`) | 0% | 173/182 (95.1%) |

Participants, start time and status are 100% on all four.

**Season and competition are already parsed and then thrown away.** `_parse_v1_season_schedule`
sets `fixture.season` and `fixture.league` from the tournament wrapper; `_claim_context` in
`stamp_v1_statpal_fixtures.py` records `league` and drops `season`. The NFL stamper records
`round` and has no season to record. Across all 1,044 StatPal game anchors on production,
**293 carry a round and 0 carry a season** — and all 293 are NFL, written by
`stamp_nfl_statpal_fixtures`. The generic v1 stamper records neither.

So closing the competition/season half of D106 costs no new ingest and no schema change:
it is two keys added to a JSONB `claim_context` the writer already builds.

---

## 3. The five rules the measurements force

These are not style preferences. Each one is a way the obvious implementation is wrong,
demonstrated on today's data.

### R1 — `stats_id` MUST NEVER ANCHOR A GAME

`stamp_v1_statpal_fixtures.py` calls this "program step 5's question", carried but
deliberately unanswered. **It is now answered: `stats_id` is not a game key.**

* **NHL** — 4 `stats_id` values each name **two different team-pairs** (8 rows). Anchoring on
  it would merge two unrelated games.
* **MLB** — 15 values each name two rows of the *same* pair (30 rows): it is a series /
  matchup key, shared across consecutive games at one venue.
* NHL's `Dallas @ Winnipeg` back-to-back on 2026-12-20 shares `stats_id=69529` across both
  legs — the same shape.

`fixture_id` anchors. `stats_id` is carried in `claim_context` and never substituted.

### R2 — THERE ARE TWO MIDNIGHTS AND ONLY ONE IS A PLACEHOLDER

* **`04:00:00Z` is midnight US Eastern and it is OUR sentinel** for a start nobody set —
  five NHL preseason rows, already found and receipted.
* **`00:00:00Z` is a real 7:00pm ET start.** 405 NHL, 266 NBA and 36 NFL fixtures sit
  exactly there. The distribution around it is smooth (NHL: 00:00 ×405, 23:00 ×200,
  01:00 ×168, 00:30 ×81) and the rows are spread evenly across the season — 47% fall after
  the season midpoint, against 49% for all rows — so they are not "far-future, time not yet
  published".

A guard written against "midnight" without saying *which* midnight either misses the five
real phantoms or deletes 671 real fixtures. Say the timezone, always.

### R3 — UNKNOWN START IS TOLD BY THE PARTICIPANTS, NOT BY THE CLOCK

StatPal's NFL `season-schedule` publishes 53 postseason placeholders reading `TBD @ TBD`,
at `00:00Z`, and **the six `fixture_id`s among them repeat up to 15 times each** — `280795`
appears 15×, `280794` 10×, each time under a different `round`. One provider id claiming to
be several different games.

Among the 322 non-placeholder NFL fixtures the id is unique, every time. So the placeholder
test is `TBD` participants (and the repeated id), not the timestamp.

**Nothing guards this today.** The stampers are safe only incidentally, because they require
both team names to match exactly and no team is called TBD. Any writer that creates from the
schedule instead of matching against it mints 52 phantoms with 6 colliding anchors — #3840's
class exactly, and EVENT-GRAPH-DOCTRINE rule 1's phantom.

### R4 — A DOUBLEHEADER IS TOLD BY THE GAP, AND THE UTC DAY BOUNDARY MANUFACTURES THEM

19 same-UTC-day same-pair groups exist right now: 18 on MLB, 1 on NHL, 0 on NBA. **Every one
is between 17.4h and 23.1h apart. Zero are doubleheader-shaped.** They are consecutive games
in a series — an evening game local time, then the next afternoon — that the UTC calendar
folds onto one date.

A true doubleheader is 3–5h apart, or ~7h for a split. So:

* group by the **venue's local date**, never the UTC date;
* the discriminator is the **gap**, with a stated threshold (< 6h ⇒ candidate doubleheader);
* two fixtures with distinct provider ids and a >12h gap are two games, and collapsing them
  loses a real fixture;
* a sport that does not play doubleheaders (NBA, NHL, NFL) never gets one from this rule,
  and a shared `stats_id` across the pair is expected (R1), not evidence of duplication.

There are no doubleheaders anywhere in the readable window today, which means any code that
produces one is producing it from nothing.

### R5 — `commence_time_source` NAMES THE WRITER, NOT THE AUTHORITY

Production distribution: `kalshi` 147,719 · `NULL` 30,414 · `polymarket` 24,791 ·
`odds_api` 14,921 · `statpal` 9,582 · `espn` 6,480 · `kalshi_ticker` 1,186 ·
`kalshi_occurrence` 55 · `mlb_schedule_repair` 3.

The largest bucket is a source whose timestamp is documented as a *close* time, not a start
(gotcha #14), and the second largest is unset. The column cannot answer "is this start
authoritative?" — it answers "who wrote it last". D106 asks for authoritative start
provenance, so provenance has to carry a **grade** alongside the writer, and `unknown` has
to be expressible rather than backfilled with a plausible-looking timestamp.

---

## 4. The contract — additive, and adoptable one client at a time

Two new **optional** objects on the event payload. Nothing existing changes shape, name or
meaning, so web and native are never forced into a simultaneous rollout: a client that does
not read `identity` behaves exactly as it does today.

```jsonc
"identity": {
  "provider_ids": [                       // every id we hold for this fixture, namespaced
    {"source": "espn",     "id": "401872656",                     "kind": "game"},
    {"source": "statpal",  "id": "americanfootball_nfl:280445",   "kind": "game"},
    {"source": "odds_api", "id": "8c94552d022acec4a0458d70c19d3da9", "kind": "game"}
  ],
  "competition": {"key": "americanfootball_nfl", "name": "NFL"},
  "season":      "2026",                  // null when the venue does not serve one (NFL today)
  "round":       "Regular Season / Week 1", // null when the venue does not serve one
  "game_number": null,                    // 1|2 for a doubleheader leg; null otherwise — see R4
  "start": {
    "at":         "2026-09-10T00:20:00Z", // null when unknown; NEVER a plausible substitute
    "provenance": "espn",                 // the writer  — R5
    "grade":      "authoritative"         // authoritative | derived | unknown  — R5
  }
}
```

```jsonc
"lifecycle": {
  "state": "scheduled",   // scheduled | live | final | postponed | cancelled | unknown
  "legacy_status": "scheduled"  // the existing `status` value, unchanged, for one release
}
```

Field-by-field, and what a client may rely on:

| field | rely on it? | why |
|---|---|---|
| `provider_ids[]` | **yes** — may be empty, never wrong | one row per `event_provider_anchors` entry of `kind='game'`, plus the three id columns. `kind` is load-bearing: only `game` asserts sameness. |
| `competition` | **yes** | 100% at the venue on all four sports |
| `season` | present-or-null | 100% on NBA/NHL/MLB, **0% on NFL** — render nothing when null, never guess a year |
| `round` | present-or-null | 100% on NFL, 0% on NBA/NHL/MLB |
| `game_number` | present-or-null | null today everywhere; set only when R4's gap test fires |
| `start.at` | **may be null** | R2/R3 — a null start is the honest answer and must render as "time TBC", never as a timestamp |
| `start.grade` | **yes** | the only field that says whether `start.at` can be trusted; `unknown` ⇒ do not print a clock |
| `lifecycle.state` | **yes** | superset of today's `status` |
| `lifecycle.legacy_status` | deprecated on arrival | present for exactly one release so nobody has to cut over on the same day |

**`postponed` does not exist today.** Production `events.status` holds only `closed` (199,806),
`completed` (16,100), `suspended` (11,844), `voided` (4,722), `scheduled` (2,577), `live` (80)
and `merged` (22). D106 requires postponements to be preserved and the schema currently cannot
say the word, so `lifecycle.state` is the place it becomes expressible. Until a writer sets it,
the mapping is `scheduled→scheduled`, `live→live`, `completed|closed→final`,
`voided→cancelled`, `suspended|merged→unknown`.

---

## 5. Who does what

* **authority** (this lane) — the producer side. Carry `season` and `round` through
  `_claim_context` in `stamp_v1_statpal_fixtures.py` (two JSONB keys, written only when the
  venue serves them, no schema change — the NFL stamper already carries `round` and the
  venue serves it no season); make R3's placeholder rejection explicit rather than relying
  on name matching; answer R1 in the code that reads `stats_id`. Owned files only; no
  registry edits.
* **lane1** — the registry and matcher side. R1 and R4 are matching invariants: an anchor
  keyed on a non-unique id, and a same-local-day pair, are the two shapes that produce a
  twin or a lost fixture. Nothing here asks lane1 to widen absorption — gotcha #32 and
  ruling 048 are untouched.
* **live** / **native** — read `identity` and `lifecycle` when they appear, ignore them when
  they do not. The one behaviour change that is not optional: **when `start.grade` is
  `unknown`, do not print a clock.** Notice 34 applies — "time TBC" is a label, not a
  paragraph explaining why we don't know.

Rollout order: producer keys first (invisible), then the payload block (inert until read),
then each client at its own pace. Data writes and canonical identity keep Tier 1 review and
attended steps (D106).

---

## 6. Not in this contract

* **Containers.** The NFL container is V2 (D106); this is one fixture, one row.
* **Off-court props** (#4500, notice 40) — a container question, not an identity one.
* **Which of NBA/NHL's two agreement denominators governs** — raised in
  `ARTIFACT-AUTHORITY-LEDGER-SPEC.md`, still Alex's.
* **Soccer and tennis availability** — not probed here; the four US sports are the release
  path. Measure before extending the table, and say the date.
