# LIVE-045 — the lowest-id Polymarket row stops vetoing its group

**PILLAR:** TRUTH · **SHIP:** 11 more US Open match pages show a Polymarket price instead of
nothing — 25/36 → 36/36 of the tournament's events, on prices the source has been publishing
the whole time.

**base:** `origin/master` `5521ef3a` · **PR:** #2702 · **repairs:** CERT-759

---

## 1. What the cert asked for, and what could actually be picked

CERT-759 withheld the token for live/041's `cd4ec4e8`:

> the actual current writer still chooses the lowest-id Polymarket row before parsing. An
> exact-head empty-parent-id-1 plus match-winner-child-id-9 reproduction returns `primary 1`
> and `reading None` … the necessary try-every-child `resolve_orientation()` repair is absent
> from both master and this two-file cut.

Per standing notice 12, the earlier GREEN on `a1fe4212` stands and this finding is its own
cert, not a reason to revert. The directive said to cherry-pick live/035's `f9e0122c`.

**That cherry-pick does not exist.** `f9e0122c` repairs
`backend/app/tasks/event_chart_backfill.py::resolve_orientation`, and that file is not on
master — the whole live/035 chain (035 / 036 / 039 / 042) is unmerged:

```
$ git ls-tree origin/master backend/app/tasks/event_chart_backfill.py
(empty)
$ git merge-base --is-ancestor 4791b80e origin/master
035 feat NOT on master
```

The writer CERT-759 reproduced against — and the only writer of the
`win_probability_sources.polymarket` number this ship is measured on — is the **shared**
`compute_source_home_probability` in `app/utils/live_blend.py`, used by both the 120s poll and
the WebSocket fast lane. `f9e0122c` deliberately did **not** touch it ("its other consumer is
the live blend"). So the same design lands at the layer the cert measured. When live/035
merges, its own copy in `event_chart_backfill.py` is a different file and does not conflict.

## 2. The defect

`select_primary_market` prefers a game winner and otherwise takes the **lowest market id**;
`is_game_winner_market` gates **Kalshi only**, so for Polymarket every row of a group scores
the same and "lowest id" means **oldest**. Polymarket mints the event-level parent and the
derivative books before the match-winner child that carries the moneyline. The writer treated
that one answer as final — parse it, resolve it, or return `None` for the whole source.

On production the parent is rarely the culprit. In **11 of the 12** blanked US Open events the
lowest-id row is the `- Exact Score` book, e.g. event 15299463:

```
59955246  Alexander Bublik vs. Adrian Mannarino - Exact Score      <- primary, reads None
59959795  US Open ATP: Alexander Bublik vs Adrian Mannarino        <- the price, never asked
```

## 3. The repair is two halves, and the second is the one that took the work

**Half one — the primary is a preference, not a verdict.** It is still asked first (so anything
that already spoke keeps saying the same thing), then the rest of the group in deterministic id
order, and the first market that can speak wins.

**Half one alone is dangerous, and this is the finding of the queue.** Polymarket decomposes a
game into rows sharing the match winner's two-outcome shape *and* its `A vs. B` title,
differing only by a qualifier. Those names **parse** — the matchup parser strips container
suffixes to recover participants — and their outcomes **are the team names**, so they
**resolve**. An ungated fallback was replayed over the 3-day population and newly stamped **95
derivatives** as the match moneyline:

| shape newly taken by an ungated fallback | count |
|---|---|
| `A vs. B - Exact Score` | 24 |
| `A vs. B - Halftime Result` | 22 |
| `A vs. B: Both Teams to Score` | 18 |
| `A vs. B - More Markets` | 7 |
| `A vs. B: Both Teams to Score in Second Half` | 2 |
| `A vs. B: First Team to Score` | 2 |
| esports / prefixed winners (correct, but refused as unrecognized) | 20 |

A halftime price on the hero, confidently, with nothing on screen to say so. Nothing downstream
would notice: it sits between 0 and 1, it moves, and it usually ends on the correct side.

**Half two — a fallback must prove it is the match.** Every non-primary candidate must classify
as `moneyline` under the ONE shared recognizer (`app/utils/game_market_class.py`), run over the
shared parser's own prefix stripping (`_strip_category_prefix`, precedent: `app/tasks/kalshi.py`).
Neither list is re-implemented — a second copy does not throw when it drifts, it quietly
disagrees (#1951).

**The primary stays exempt, and that is load-bearing rather than lazy.** Gating it too was run
as a mutation over the banked population: **199 live readings lost**, 48 of them non-ASCII
names like `FC Nordsjælland vs. Aarhus GF` that the recognizer's ASCII-only team pattern
cannot match. A control test pins the exemption.

`select_primary_market` is **not** changed — it is also the poll's row-picker, a second caller
this queue did not measure. The poll's `game_state` audit trail now stamps `reading.market`,
because the primary is no longer always the market the number came from and "why did the blend
say that" has to name the one that said it. (`live_blend_refresh.py` already did this.)

## 4. Measurement — two arms, two processes, complete populations

Each arm loads `app.utils.live_blend` from an explicit path under the canonical module name in
its **own process**; one interpreter would share `sys.modules` and let the second arm grade the
first arm's code. Payload pulled from production 2026-09-02 via `db-query`, hash-chunked, and
**every chunk asserted un-truncated**.

### The ship — every US Open event carrying a Polymarket market

36 events / 360 markets / 698 outcomes — the complete population, not a sample.

| | before | after |
|---|---|---|
| groups producing a reading | **25 / 36** | **36 / 36** |
| ADDED | — | **11** |
| LOST | — | **0** |
| CHANGED | — | **0** |

All 11 additions come from the `US Open ATP: A vs B` match winner. Not one from a prop.

Live production state of `win_probability_sources ? 'polymarket'` on the same population:

| status | before | after (this PR) |
|---|---|---|
| live | 4 / 4 | 4 / 4 |
| scheduled | 17 / 25 | **25 / 25** |
| completed | 3 / 7 | **7 / 7** |
| **total** | **24 / 36** | **36 / 36** |

The directive's morning figures (live 4/4, scheduled 5/26, completed 0/6) had already moved
before this branch started — `a1fe4212` deployed and the 2-minute poll ran — so the before
column is **re-measured at this branch's base**, not inherited. One event moved
scheduled → completed in the interval; the population is the same 36.

The 12th blank event (15298238, Virtanen vs Rublev, completed) resolves in **both** arms of
the replay: its silence in production has a different cause and is not this defect. It is
covered here anyway.

### Blast radius — this is the shared writer

All events with a Kalshi or Polymarket market in a 3-day window: 2,027 events / 8,053 markets /
16,061 outcomes.

| | before | after |
|---|---|---|
| (event, source) groups producing a reading | **826 / 2,197** | **919 / 2,197** |
| ADDED | — | **93** |
| LOST | — | **0** |
| CHANGED | — | **0** |
| ADDED not classified `moneyline` | — | **0** |
| ADDED from Kalshi | — | **0** |

Raw diff banked at `artifacts/live/LIVE-045-TWO-ARM-REPLAY.json`.

## 5. Gates

| gate | result |
|---|---|
| red-first, same guard file both arms | master **10 failed / 21 passed** → branch **31 passed** |
| mutation: drop the fallback gate | **12 red** (incl. the 6 derivative tests green in both arms), 18 green |
| mutation: gate the primary too | exemption control **red**; costs 199 real readings |
| `ruff check` (both changed files + new test) | clean, exit 0 |
| `pytest tests/test_startup.py` | **4 passed**, exit 0 |
| full backend suite | see the PR |
| frontend / iOS | **no file in the diff** — those gates cannot move and were not run |

The guard file drives only the public `compute_source_home_probability`, never the new private
helpers, so it imports and runs under both arms: the red-first result is a real assertion
failure, not an `ImportError` wearing one.

The 6 derivative-safety tests pass in **both** arms (master never falls back at all), which
would make them vacuous as arm evidence. The gate-removal mutation is what proves they are
load-bearing.

## 6. Named, not smuggled in

- **40 more groups** stay silent only because `game_market_class`'s team-token pattern is
  ASCII-only. That classifier has four other consumers (game-markets endpoint, calibration
  cohorts, capture census, this writer); widening it is its own ship with its own blast radius.
- Some groups whose **primary** is a derivative already write a derivative-based reading on
  master (`Paris FC vs. Olympique Lyonnais - Exact Score` among them). Pre-existing; narrowing
  it here would break this branch's "can only widen" claim.
- The **463** US Open Polymarket rows filed as `table_tennis` are **lane1/055's**. Sport
  classification untouched (ONE OWNER).
- **Not a D35 matching change:** no linkage, no `event_id`, no registry call. Every market
  here is already linked; the change is only about which linked market speaks for its source.

---

# ROUND 2 — the CERT-767 repair: the shared decision reaches the writer that ships it

CERT-767 withheld the token for `9bd6dbe5` and was right. Everything above is about
`live_blend.compute_source_home_probability`, and everything above holds. The cert's point is
that **that helper is not the writer the ship is measured on.**

## 7. What CERT-767 found

> the 15-minute matching task still independently picks and parses only the lowest-id Polymarket
> row before writing `win_probability_sources`; exact-head reproduction yields primary id 1 / no
> matchup while the repaired helper selects child id 9 at 0.62.

`_match_prediction_markets` Phase 2 carried its own inline copy of the arithmetic — primary
selection, matchup parse, moneyline resolution, devig — and asked the primary and nothing else.
That is the CERT-759 veto, intact, in the one writer that reaches a **scheduled** event. The live
poll only ever selects live events and the three hours before commence, so the Round-1 repair was
reachable for a handful of live matches and unreachable for the twenty-five scheduled ones the
queue exists for. Round 1 fixed the decision; it did not fix the caller that ships it.

The cert's second finding is a window, not a copy: Phase 2 admits a completed event only for its
first 24 hours and the live poll never admits one, so a group vetoed *during* the game has no
second chance *after* it.

## 8. The two repairs

**8a. Phase 2 asks the group, through the one shared decision.** The inline block is replaced by
`_phase2_persist_group_reading`, which loads the outcomes of every market in the (event, source)
group in one query and hands the whole group to `compute_source_home_probability`. The reading
that comes back names the market that spoke, and that market's id is what the snapshot's
`game_state` records.

What deliberately did **not** move: the two Kalshi unlink arms. Those are decisions about a
row's LINK, not about what the source says, and `test_kalshi_ticker_eastern_window_q439` and
`test_ws_liveness_and_segment_unlink_q504b` scan `_match_prediction_markets` itself for them.
The caller still computes the primary and still runs both arms on it, exactly where they run
today; only the reading was extracted.

**8b. `_phase2b_completed_catchup`** — a bounded pass over completed events that aged past Phase
2's 24-hour window. Three safety properties, each with its own guard and its own killed mutation:

- **No snapshot.** Blend key only. The chart's completed journey is byte-for-byte unchanged and
  the "prediction market bleed" fix (0t-1) is untouched.
- **Holes only.** The candidate query demands the source key be ABSENT, so the pass can add a
  reading where the source said nothing and can never move a number already on screen — the same
  strictly-additive property the Round-1 repair has.
- **Bounded, and actually advancing.** A 7-day floor, 75 events per source per run, and the
  task's own clock. The rotation is the part that took the thinking: a candidate the helper
  legitimately REFUSES never gets a key, so it never leaves the candidate set, and a plain
  `ORDER BY commence_time ASC LIMIT 75` hands back the same page every fifteen minutes forever.
  Measured — the first production page of this query is 75 Brazilian lower-division rows whose
  own `away_team_name` ends `- Halftime Result`, behind which US Open 15298238 sits unreachable.
  So the page start is a Redis cursor, advanced past each page and wrapped to the floor when the
  scan runs dry. A refused row costs one rotation, not the sweep.

It never unlinks: this pass reads settled rows and repairs nothing, so it gets no destructive verb.

## 9. Measurement — the WRITER replayed, two arms, two processes

Round 1 replayed the helper. This replays **the writer**, over the complete population Phase 2
actually selects: `scheduled`/`live` plus `completed`/`closed` inside 24h, both sources.

    population   1,054 events / 5,191 markets / 31,735 outcomes    no chunk truncated
    arm master   the inline block transcribed verbatim from master's source
    arm branch   _phase2_persist_group_reading's decision
                 (each arm in its own interpreter, from its own tree)

    1,196 groups     spoke 606 -> 655     ADDED 49    LOST 0    CHANGED 1

All **49** additions are Polymarket, all **49** classify `moneyline` under the shared recognizer,
and **not one** carries a derivative token (`- Halftime`, `- Exact Score`, `Both Teams to Score`,
`Set N`, `O/U`, `Handicap`, `Spread`). By status: 32 scheduled, 12 closed, 4 completed, 1 live.

**The one CHANGED is a fix, and it is worth naming.** Phase 2's old devig was UNGATED — it
averaged the primary with any sibling that resolved, where the shared helper requires a Kalshi
sibling to be a game winner too. Routing Phase 2 through the helper inherits that gate:

    15291920 kalshi   Flamengo vs Mirassol    0.6350 -> 0.8400

0.6350 is exactly `(0.84 + 0.43) / 2` — the match winner averaged with the market's
`Flamengo vs Mirassol: BTTS` "Yes" price. A number belonging to neither question was being
stamped as the moneyline. Across the current population four Kalshi groups sat in that shape
(`1st Half Winner`, `Total Goals`, `BTTS`, and a *What will the announcers say during Royal
Rumble* row mislinked onto Kansas City vs Seattle); one of them moves the published number.

### The ship, on production, before

`US Open` Polymarket markets, events grouped by status (2026-09-02, after `a1fe4212` merged):

| status | events | carrying a `polymarket` blend key |
|---|---|---|
| live | 6 | 6 |
| scheduled | 25 | 17 |
| completed | 8 | 4 |
| **total** | **39** | **27** |

Eleven of the twelve blank groups lead with a **zero-outcome** `- Exact Score` book at the lowest
id, with the match winner minted next — the veto shape, exactly. The replay above turns all
eleven on (they are the 11 US Open rows inside the 49). The twelfth, **15298238**, holds a
readable winner at 0.165 and is blank only because it completed on 08-31; it is the catch-up's.

## 10. Gates — round 2

| gate | result |
|---|---|
| new guard file, red-first (master tree, master code) | **27 failed / 1 passed** → branch **28 passed** |
| mutation battery, 11 mutations | **11 killed, 0 survivors** |
| adjacent band (matching / phantom / q435 / q439 / q504b / settled-budget / beat wiring) | **573 passed** |
| blend + market + snapshot band | **2,643 passed**, 11 skipped |
| `ruff check` on the changed task module | **14** — identical to master's baseline |
| `pytest tests/test_startup.py` | **4 passed** |
| full backend suite | see the PR |
| frontend / iOS | **no file in the diff** — those gates cannot move and were not run |

**The mutation that mattered.** The first battery had a survivor: reverting the Phase 2 CALL SITE
to `[market]` left all 21 tests green, because every behavioural test drives
`_phase2_persist_group_reading` directly. A fully repaired writer handed one row reproduces
CERT-759 exactly. The wiring is the ship, so the wiring got its own assertion
(`test_the_loop_hands_over_the_GROUP_and_not_the_primary_alone`) and the mutation now kills.

**One both-arm control, and the file says so.** `test_both_kalshi_unlink_arms_are_still_inline`
passes on master too — it is what proves extracting the reading did not carry a link arm out with
it. Every other test drives a function master does not have, so master cannot green them; their
strength is the mutation record, not an arm crossing. The file states this rather than labelling
27 symbol-missing failures as controls.

## 11. Still named, still not smuggled in

- The **463** US Open Polymarket rows filed as `table_tennis` remain **lane1/055's**. Untouched.
- The **40 ASCII-only** `game_market_class` groups from Round 1 are still filed, still not fixed here.
- **New, and disclosed:** the completed catch-up will add a `polymarket`/`kalshi` blend key to
  events across every sport, not only tennis — ~2,690 events sit in the 7-day cohort today, of
  which only those with a readable winner will ever fill. Source-disagreement audits may see new
  WATCH cells on settled events as a result. That is a measurement-lane consequence of filling a
  hole, not a new disagreement.
