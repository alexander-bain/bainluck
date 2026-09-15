# native/182 — #6440: one finished-game age rule, two native feeds

PILLAR TRUTH · SHIP: the phone's Sports tab stops rendering games that finished
yesterday, on the same rule the web client uses.

sha `53f2f2e8b7287bc9630fb0078b12cf4ae71abac9` · PR #6450 · branch
`native/182-6440-one-finished-age-rule`, rebased on master `422daac0d`.

## The defect, re-measured on the live payload before building

`GET /api/feed?mode=sports&limit=40`, 2026-09-15 ~22:50Z — 40 items, 6 finished
events, one of them **18.3h old**:

| slot | id | `ended_at` | age | `discover_marquee_final` |
|---|---|---|---|---|
| 9 | 15308141 | 20:42:59Z | 2.4h | absent |
| 16 | 15301294 | 20:38:00Z | 2.5h | absent |
| 18 | 15307345 | 20:42:59Z | 2.4h | absent |
| **30** | **15312206** | **04:47:26Z** | **18.3h** | absent |
| 31 | 15308140 | 18:14:15Z | 4.9h | absent |
| 37 | 15298811 | 20:43:31Z | 2.4h | absent |

`ended_at` is served on every finished row in `mode=sports`;
`discover_marquee_final` is not stamped on that surface at all, so every one of
these reads as the ordinary 8h window — which is what web does with them.

## The LOOK — and the correction to "this render is unpayable"

#6440 says the Sports tab cannot be photographed because the router has no route
to a bare tab. **It is photographable today**: `Tab.feed` IS the Sports tab
(`MainTabView.swift:26-28`), and `NavigationCoordinator.handleURL`'s
`case "events"` already selects it for a bare `bainluck://events` — the route
LiveGamesWidget's tap-through hands out. So:

    tools/native-shoot.sh sports 'bainluck://events' --scroll 1800

No router change was needed and none was made. Shots in this directory, iPhone 17
simulator, taken ~2 minutes apart against the same live feed:

| file | build | what it shows |
|---|---|---|
| `sports-before-s2000.png` | master `422daac0d` | "Just Happened" ends with **NFL Broncos 10 – Chiefs 31, Sep 14**, WTA Guadalajara **Sep 14**, Brazil Série B **Sep 14** |
| `sports-after2-s1800.png` | this sha | the same region: the last finished card is Sep 15, then "Top Markets" — the Sep 14 rows are gone |
| `sports-after.png` | this sha | the tab as it opens: Live Now, unchanged |
| `sports-after-s1400.png` | this sha | the finished section: every card Sep 15 |

Read as a first-time reader: the before shot puts last night's NFL final under a
heading that says the game just happened, two rows below a game that is live. The
after shot ends the section on today's games. Nothing else on the tab moved.

## Gates on the shipping sha

- `tools/native-gates.sh`: macOS build PASS · recompile proof on all 4 changed
  Swift files · `Executed 2430 tests, with 0 failures (0 unexpected) in 34.111
  (35.114) seconds`
- `npm run build` exit 0 · `npm run typecheck` exit 0 (`typecheck errors: 70
  (baseline 70)`) · `npx jest --testPathPatterns=finishedCardAgeParity` 5 passed
- CodeQL check-run: `success — No new alerts in code changed by this pull request`

## Mutation check — 6 built, 6 killed

Scoped runs of `SportsFinishedAgeOut6440Tests` (17 tests) with the fix mutated:

| mutant | failures |
|---|---|
| boundary `>` → `>=` | 1 |
| anchor order → kickoff first | 3 |
| marquee `== true` → `!= false` | 5 |
| rendered bucket un-gated (`filteredJustHappened` reverted) | 2 |
| reprieve always on | 8 |
| Discover restored to its 8h-from-kickoff rule | 1 |

Tree restored and re-gated after the last mutant.

## What this ship did NOT take

- `MyStuffViewModel.justHappened` and `SportCategoryViewModel.justHappened` have
  no age term either. A pinned game and a league page are different questions
  from "the Sports feed is showing yesterday"; the shared predicate makes either
  a one-line adoption if it is ruled wanted.
- Web's `applyFinishedCardGuard` also deletes **settled futures** from `/sports`,
  and native's Sports tab has no gate on `topMarkets` at all. Inferred from the
  source, not seen on a screen, so it is noted on #6440 rather than filed or
  widened into this ship.
