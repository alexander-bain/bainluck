"""Stamp every NBA, NHL and MLB row with the StatPal contest it is. #2867 / D50.

**SHIP: an NBA, NHL or MLB game page can eventually show StatPal's
period-by-period truth instead of a second-hand score, because the game on screen
is now joined to the StatPal contest that carries it. The join is DARK — nothing
reads it — and it is the measurement that decides whether it may ever be read.**
(Pillar: MATCHING.)

Program step 2 did this for the NFL (`tasks/stamp_nfl_statpal_fixtures`). Step 3
did it for the two sports that share StatPal's *flat v1 season-schedule* shape,
and one module serves them because they are the same problem: one call returns
the schedule as `scores.tournament.match[]`, both sides spell the franchises
identically, and `time` is UTC on it. Step 5 adds MLB, the third. NFL keeps its
own module — its payload nests three levels deeper, it is the only sport with
`datetime_utc` on the schedule, and it is in front of the bus.

WHAT MLB BROUGHT WITH IT, 2026-09-04 (step 5)
═════════════════════════════════════════════
MLB was held out of `V1_SEASON_SCHEDULE_SPORTS` on the grounds that its ids "do
not survive between endpoints". Measured, they do — but only under a name nobody
had looked at, and the three things that came out of resolving it are all
widenings of this module rather than exceptions carved into it.

1. **THE ANCHOR IS `livescores.oddsid`, NOT `livescores.id`.** 13 of 16 live rows
   carry it and 13/13 dereference to a `season-schedule.id`. `livescores.id` is a
   genuinely separate space, and it is a trap: it and `season-schedule.stats_id`
   are both ten digits, both begin `1329`, and their ranges overlap — with **not
   one value in common** (0/16, and 0 of our 222 stored column values). Any rule
   that reads a space off a number's shape joins those two confidently and
   wrongly, which is the measured MLB case for D55. Hence
   :data:`LeagueSpec.live_anchor_field`: named per league, never inferred.

2. **OUR COLUMN ALREADY HOLDS TWO ID SPACES AT ONCE**, because
   `_parse_single_fixture` takes `fixture_id` from `id` and `id` means different
   things on the two endpoints — so the schedule sync and the live sync have been
   writing different spaces for the same sport. Of 222 distinct MLB column values
   on production, 130 dereference to `season-schedule.id`, **0** to `stats_id`,
   and 92 to neither. That is not a matching error and must not be filed as one:
   see :data:`VERDICT_FOREIGN_ID_SPACE`.

3. **`stats_id` COVERAGE IS NOT A BOOLEAN.** NHL 1404/1404, NBA 0/1206, MLB
   **198/227**. The field was a `bool` and MLB does not fit in it; it is now
   three-valued, with the rate recorded beside it (:data:`STATS_ID_ON_SOME_FIXTURES`).

And one thing MLB does NOT share with the other two: **its schedule is a rolling
~17-day window, not a season.** 227 games on 2026-09-04, a different 227
tomorrow. Every denominator taken from it is a window, and comparing one day's to
another's is comparing two different fortnights.

WHAT WAS MEASURED FIRST, 2026-09-04 ~5:10am PT
══════════════════════════════════════════════
The directive for this step says: *do the NFL lesson first, not last — measure
how far apart the two sides' start times actually are before choosing a window.*
Live `GET /v1/{nba,nhl}/season-schedule` against production `events`:

    league  StatPal  ours in-window  same-orientation join  swapped  no key
    NBA      1206         41               41 / 41              0       0
    NHL      1404         32               32 / 32              0       0

    kickoff delta, StatPal minus ours
    NBA   41 of 41 agree TO THE MINUTE
    NHL   25 of 32 to the minute, 1 at +0:30, 1 at +1:00, and FIVE at +18:30…+22:00

Three findings came out of that table, and each one is a decision below.

1. **±1 HOUR IS THE MEASURED CEILING, NOT A HABIT INHERITED FROM THE NFL.**
   In both leagues the same pair meets twice, in the same orientation, **23 hours
   apart** — NBA `Oklahoma City @ Portland` on 2026-11-11 04:00Z and 2026-11-12
   03:00Z; NHL `Dallas @ Winnipeg` on 2026-12-20 00:00Z and 23:00Z. Those are real
   back-to-backs at one venue. A window wider than **11.5h** can therefore reach
   both meetings of a back-to-back and stamp a game with the next night's contest.
   ±1h is well inside that and captures every honest kickoff either side serves.

2. **The five NHL outliers are OUR clock, and they are above the safe ceiling.**
   All five sit at exactly `04:00:00Z` — midnight US Eastern — on 2026-10-01 and
   2026-10-02 preseason rows, against StatPal times 18.5–22h later. That is our
   placeholder for a start time nobody has set, not a broadcast correction. They
   cannot be stamped by ANY window that is safe against finding 1, so they are
   receipted as unmatched rows and filed. Saying so here is the point: NFL's
   equivalent — 30 rows behind an unset Weeks 16–18 kickoff — was discovered as a
   76%-vs-99% surprise, and this one is stated before it can be one.

3. **The agreement number for these two sports is NOT about identity, and the
   ledger spec's denominator makes it unreachable.** StatPal publishes the whole
   season on day one (1206 / 1404); we hold only games that have odds posted
   (41 / 32). Under `ARTIFACT-AUTHORITY-LEDGER-SPEC.md`'s NBA rule 5 — *denominator:
   all 1206 scheduled games* — identity reads **3.40%** for NBA and **2.28%** for
   NHL and can never approach D50's 99.5%, for a reason that is not a disagreement.
   Of the games WE hold, StatPal has **41/41 and 32/32**. Both numbers are
   published, neither is blended, and which one should govern is a question for
   Alex, raised in the artifact — not something this file quietly decides.

WHAT "SHADOW" MEANS HERE, PRECISELY
═══════════════════════════════════
Identity, never content. No score, no status, no start time, no team, and **it
never creates a row.** Every write is an `UPDATE` of an event that already exists,
plus its anchor. A StatPal fixture we hold no row for is a *receipt*, not an
insert: ruling 048 is unmoved, and the honest answer to "StatPal has a game we
don't" is to say so, because that is a finding about our ingestion.

THE STATE THESE TWO SPORTS ARE ALREADY IN, WHICH THE NFL WAS NOT
════════════════════════════════════════════════════════════════
`tasks/statpal_sync` already writes `events.statpal_fixture_id` for NBA and NHL —
the shared ingestion parser was never blind to them the way it was to the NFL.
Measured on production 2026-09-04:

    NBA  324 of 783 rows hold a real digit id      NHL  367 of 705
    StatPal anchors for either sport                0

So the majority state for these sports is *column set, anchor absent* — precisely
the state `anchor_channel.anchor_is_current` reads as STALE, which resolves
nothing while looking like a link. A stamper that treated a correct column as
"already linked" and moved on would leave that state forever. Hence
:data:`VERDICT_ANCHOR_ONLY`: when the column already holds exactly this contest's
id, the anchor alone is written and the pair is completed.

(The 691 already-populated rows are last season's — games from 2026-02 to 2026-06 —
and StatPal's `season-schedule` serves only 2026/2027, so no pass can verify or
anchor them. They are out of every window this task will ever see.)

FOUR THINGS ONE STATPAL CONTEST CAN BE AGAINST OUR TABLE
════════════════════════════════════════════════════════
    column is empty                    -> STAMP          write column + anchor
    column == this contest's id        -> ANCHOR_ONLY    write the anchor
    column is a digit id, but another  -> CONTRADICTION   write nothing, receipt
    column is not an id at all (#2963) -> POLLUTED_COLUMN write nothing, receipt

`CONTRADICTION` is a bucket the NFL module has no use for and this one needs: the
ingestion path picks its match by its own rule, so a disagreement between its
answer and ours is the first evidence that one of the two rules is wrong. Folding
it into "already linked" would spend that evidence.

THE SECOND ID, AND WHY IT IS LOGGED RATHER THAN ANCHORED
════════════════════════════════════════════════════════
NHL serves `stats_id` on 1404/1404 games and it is a genuinely different number
from `id` (`649052` ↔ `68933`). NBA serves the key on all 1206 games and **empty
on all 1206** — `docs/statpal-capabilities.md`'s joint "`id` + `stats_id`" credit
is wrong for NBA. Which of the two anchors a game is program step 5's question
(the MLB three-id problem), so this task anchors on `id`, carries `stats_id` into
the anchor's claim context where it is visible, and receipts the day either
league's coverage of it changes.

Related, and measured because D55 forbids guessing it: our column holds 6-digit
NBA ids on games up to 2026-04-11 and 7-digit ids from 2026-04-12 on. That is not
two namespaces — it is **one counter that crossed 1,000,000 on 2026-04-05**. The
digit count is a function of the date, which is exactly why the anchor key is
qualified by sport and never derived from the id's length.

RECEIPTS RUN IN BOTH DIRECTIONS
════════════════════════════════
A StatPal contest we hold no row for is an *ingestion gap*. One of our rows that
no contest matched is a *candidate phantom* — and for these two sports it is also
where the five midnight-placeholder NHL rows show up. Reporting only the first
direction would hide them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    WROTE,
    record_anchor,
)
from app.services.authority_ledger import record_agreement_day
from app.services.statpal_api import StatPalFixture, get_statpal_service
from app.utils.authority_agreement import (
    Side,
    build_agreement_row,
    measurement_bounds,
)
from app.utils.nfl_team_matching import normalize_team, pair_matches
from app.utils.provider_anchor_keys import statpal_anchor_key, statpal_id_space
from app.utils.statpal_league_rosters import is_known_league_team

logger = logging.getLogger(__name__)


#: What a league was MEASURED to do with `stats_id`, StatPal's second id.
#:
#: This was a `bool` until MLB arrived, and MLB is why it is not one: NHL serves
#: it on 1404/1404 and NBA on 0/1206, but **MLB serves it on 198 of 227 —
#: 87.2%**, which is neither. Rounding that to a boolean would either forge a
#: promise the provider does not keep or throw away 198 real ids, and letting a
#: half-configured sport exist is the thing :class:`LeagueSpec` was written to
#: prevent. So the field is three-valued and MLB's rate is recorded beside it.
#:
#: The 29 blanks were checked for structure before this widening was accepted,
#: because a rule would have beaten a rate: they are NOT "filled once played".
#: Measured over the full 227-game census, `Finished` games are filled 52/70
#: (74.3%) and `Not Started` games 146/157 (93.0%) — the blanks are commoner on
#: games already played, scattered across all 18 dates. There is no rule to
#: find, so the honest expectation is "some".
STATS_ID_ON_EVERY_FIXTURE = "on every fixture"
STATS_ID_ON_NO_FIXTURE = "on no fixture"
STATS_ID_ON_SOME_FIXTURES = "on some fixtures"

#: The field on `livescores` that carries the id in the SAME space as
#: `season-schedule.id`. Named per league and never inferred (D55).
LIVE_ANCHOR_IS_ID = "id"
LIVE_ANCHOR_IS_ODDS_ID = "oddsid"


@dataclass(frozen=True)
class LeagueSpec:
    """One league's answers to the questions this task asks per sport.

    A dataclass rather than parallel dicts so that adding a sport is one literal
    with every question answered, and a half-configured sport cannot exist. MLB
    (step 5) is the case that proves the shape earns its keep: it answered two of
    these questions differently from both incumbents, and both differences had to
    be widenings rather than exceptions.
    """

    #: Our `sports.key`, and — because all three leagues are 1:1 with StatPal's
    #: own sport name — the id space too. `statpal_id_space` is still asked
    #: rather than assumed, so the day a sport stops being 1:1 (tennis already
    #: has) there is one place to fix.
    sport_key: str
    #: StatPal's sport token: the `{sport}` in `/v1/{sport}/season-schedule`.
    statpal_sport: str
    #: For logs and receipts.
    label: str
    #: One of the three `STATS_ID_ON_*` constants. An EXPECTATION, so the pass
    #: reports the day the answer changes instead of silently absorbing it.
    stats_id_coverage: str
    #: The measurement the expectation was set from, verbatim, so a receipt can
    #: say what changed and not merely that something did.
    stats_id_measured: str
    #: Which `livescores` field carries the anchor-space id for this league.
    #:
    #: NBA and NHL serve one space and `id` is it. **MLB serves `id` in a space
    #: `season-schedule` never publishes** — measured 2026-09-04, 0 of our 222
    #: stored MLB column values dereference to `stats_id` and 85 dereference to
    #: nothing at all — and carries the anchor under `oddsid` instead. The two
    #: are indistinguishable by shape: both ten digits, both `1329…`, overlapping
    #: ranges, not one value in common. Hence a named field per league.
    live_anchor_field: str = LIVE_ANCHOR_IS_ID


NBA = LeagueSpec(
    sport_key="basketball_nba",
    statpal_sport="nba",
    label="NBA",
    stats_id_coverage=STATS_ID_ON_NO_FIXTURE,
    stats_id_measured="0/1206 season-schedule games, 2026-09-04",
)
NHL = LeagueSpec(
    sport_key="icehockey_nhl",
    statpal_sport="nhl",
    label="NHL",
    stats_id_coverage=STATS_ID_ON_EVERY_FIXTURE,
    stats_id_measured="1404/1404 season-schedule games, 2026-09-04",
)
MLB = LeagueSpec(
    sport_key="baseball_mlb",
    statpal_sport="mlb",
    label="MLB",
    stats_id_coverage=STATS_ID_ON_SOME_FIXTURES,
    stats_id_measured="198/227 season-schedule games (87.2%), 2026-09-04",
    live_anchor_field=LIVE_ANCHOR_IS_ODDS_ID,
)

#: By our `sports.key`, which is how the beat entries and the agreement endpoint
#: name a sport.
LEAGUES: dict[str, LeagueSpec] = {
    NBA.sport_key: NBA,
    NHL.sport_key: NHL,
    MLB.sport_key: MLB,
}

#: How far apart a StatPal start and ours may be and still be one game.
#:
#: **Measured, and bounded from above by the schedule itself.** Both leagues run
#: back-to-backs where the same pair meets twice in the same orientation 23 hours
#: apart, so any window over 11.5h can reach the wrong meeting. Inside that
#: bound, ±1h covers every honest disagreement observed: NBA agrees to the minute
#: on 41 of 41, NHL on 25 of 32 with two more inside the hour.
#:
#: It is NOT a knob to widen when something fails to match. The five NHL rows it
#: misses are 18.5–22h out because OUR side stamped midnight-Eastern on a start
#: nobody has set; widening past 11.5h to catch them would buy those five at the
#: price of every back-to-back in two leagues.
#:
#: **MLB tightens the ceiling by nearly threefold and ±1h still fits under it.**
#: Baseball's back-to-back is the doubleheader, and the one in the 2026-09-04
#: window — Detroit at Cleveland — is **8.08h** apart, so nothing above 4.04h is
#: safe for this sport. That MLB's bound is the tightest of the three is the
#: reason to state it rather than inherit the NHL number: the constant is shared,
#: but the argument for it has to be re-made per league, and one day a league
#: will come along that ±1h is too wide for.
MATCH_WINDOW = timedelta(hours=1)

#: The closest two meetings of ONE pair in the SAME orientation, per league, so
#: the reasoning above is a constant a test can pin rather than a paragraph.
#:
#: Per league and not one number, because the three leagues' schedules are not
#: alike and averaging them would hide the binding one. NBA and NHL run true
#: back-to-backs at one venue a night apart; MLB's is the doubleheader, and it is
#: nearly three times tighter than either.
CLOSEST_SAME_PAIR_SEPARATION: dict[str, timedelta] = {
    #: Oklahoma City @ Portland, 2026-11-11 04:00Z and 2026-11-12 03:00Z.
    "basketball_nba": timedelta(hours=23),
    #: Dallas @ Winnipeg, 2026-12-20 00:00Z and 23:00Z.
    "icehockey_nhl": timedelta(hours=23),
    #: Detroit @ Cleveland, 2026-09-04 — the one genuine doubleheader in the
    #: 227-game window, and the tightest pair any league here serves.
    "baseball_mlb": timedelta(hours=8, minutes=5),
}

#: The largest window still safe against the TIGHTEST pair across every league
#: this module serves. A window is only as safe as the closest two contests it
#: can reach, so this takes the minimum rather than each league's own — one
#: shared `MATCH_WINDOW` has to clear the worst case, not the average one.
BACK_TO_BACK_SEPARATION = min(CLOSEST_SAME_PAIR_SEPARATION.values())
MAX_SAFE_WINDOW = BACK_TO_BACK_SEPARATION / 2

#: How far either side of the read fixtures the candidate query reaches.
CANDIDATE_SLACK = MATCH_WINDOW

#: Every row for the league in the window, linked or not, with its column value.
#: Deliberately NOT filtered to `statpal_fixture_id IS NULL` — that guard is what
#: makes an already-populated column invisible, and for these two sports the
#: populated column is the majority state.
CANDIDATES = """
SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time,
       e.statpal_fixture_id, e.status
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.commence_time >= :window_start
   AND e.commence_time <= :window_end
"""

SET_FIXTURE_ID = """
UPDATE events
   SET statpal_fixture_id = :fixture_id
 WHERE id = :event_id
   AND statpal_fixture_id IS NULL
"""


def is_statpal_contest_id(value: Optional[str]) -> bool:
    """Is this column value a StatPal id at all, or `statpal_live_...` (#2963)?

    All-digits, which is what every measured StatPal id space is. Deliberately
    not a length check: NBA's own ids are 6 digits before 2026-04-05 and 7 after,
    because the counter crossed a million — a length rule would give a confident
    wrong answer on one side of that date.
    """
    if value is None:
        return False
    token = str(value).strip()
    return bool(token) and token.isdigit()


#: The things one StatPal contest can be against our table. A verdict, not a
#: score.
VERDICT_STAMP = "STAMP"
VERDICT_ANCHOR_ONLY = "ANCHOR_ONLY"
VERDICT_CONTRADICTION = "CONTRADICTION"
VERDICT_POLLUTED = "POLLUTED_COLUMN"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNMATCHED = "UNMATCHED"

#: The column holds a digit id that this pass's authority endpoint cannot
#: resolve AT ALL — it names nothing in the id space the anchor is written in.
#:
#: Separated from `CONTRADICTION` because the two are different bugs with
#: different owners, and folding them would file 85 namespace rows as matching
#: errors. `CONTRADICTION` says *the ingestion path picked a different GAME* —
#: one of two matching rules is wrong. This says *the ingestion path may well
#: have picked the right game, and wrote its id from the wrong ENDPOINT*.
#:
#: MLB is why it exists. `_parse_single_fixture` takes `fixture_id` from `id`,
#: which on `season-schedule` is the anchor and on `livescores` is a different
#: number entirely — so `sync_statpal_schedules` and `sync_statpal_live_scores`
#: write two id spaces into one column for the same sport. Measured on
#: production 2026-09-04 over the 17-day window: of 222 distinct MLB column
#: values, 130 dereference to `season-schedule.id`, **0** to `stats_id`, and 92
#: to neither.
#:
#: The membership test is a DEREFERENCE against the ids this pass actually read,
#: never a digit count or a range — that is the whole of D55, and on MLB the two
#: spaces are the same width with the same prefix, so shape would answer
#: confidently and wrongly.
VERDICT_FOREIGN_ID_SPACE = "FOREIGN_ID_SPACE"

#: `_write_link`'s own outcome for "the column was claimed between the candidate
#: query and the write". Not an anchor outcome — `anchor_channel` never returns
#: it — so it is named here rather than borrowed from there.
LOST_RACE = "LOST_RACE"

#: The ONLY two anchor outcomes that mean the anchor names this event, so the
#: only two under which a column write may be committed. A whitelist, not a
#: blacklist: a new outcome added to `anchor_channel` must be considered here
#: explicitly, and until it is, it refuses and is receipted.
COMMITTABLE_OUTCOMES = frozenset({WROTE, CONFIRMED})


@dataclass
class StampRun:
    """What one pass did, in terms a receipt can be written from.

    Every fixture read and every candidate row lands in exactly one bucket. A run
    that reports only its successes cannot tell "StatPal published nothing" from
    "we matched nothing", and those need different fixes.
    """

    sport_key: str = ""
    fixtures_read: int = 0
    rows_in_window: int = 0
    #: Rows in the WIDER agreement-row population (`measurement_bounds`). Beside
    #: `rows_in_window` rather than replacing it: the gap between the two is how
    #: much of our inventory the write window cannot see, and for a rolling
    #: provider that gap is the whole reason the row's denominator moved.
    rows_measured: int = 0
    stamped: int = 0
    #: Column already held this exact contest; the missing anchor was written.
    anchored_only: int = 0
    #: Column already held this contest AND the anchor already named this event.
    already_linked: int = 0
    #: Column holds a DIFFERENT digit id from the contest that matched. The
    #: ingestion path and this task disagree; neither is overruled here.
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    #: Column holds a fabricated `statpal_live_...` value (#2963). Never written.
    polluted_column: list[dict[str, Any]] = field(default_factory=list)
    #: Column holds a digit id in a space this endpoint does not publish — the
    #: right game with an id read off the wrong endpoint, most likely. Never
    #: written and never overwritten: repairing it is a data write with its own
    #: backup and restore line (D51), not a side effect of a dark stamper.
    foreign_id_space: list[dict[str, Any]] = field(default_factory=list)
    #: Two of our rows for one StatPal contest. D35: filed, not resolved.
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    #: StatPal has this contest and we hold no row for it — an ingestion gap.
    unmatched_fixtures: list[dict[str, Any]] = field(default_factory=list)
    #: We hold this row and no StatPal contest matched it — a candidate phantom,
    #: or a row whose start time nobody has set.
    unmatched_rows: list[dict[str, Any]] = field(default_factory=list)
    collisions: list[dict[str, Any]] = field(default_factory=list)
    #: Candidate found, write went through, ANCHOR write refused. Rolled back.
    write_refusals: list[dict[str, Any]] = field(default_factory=list)
    #: A team name on either side that is not one of the measured 30/32.
    #: Reporting only — the match never consults the roster.
    unknown_team_names: list[str] = field(default_factory=list)
    #: `stats_id` coverage against what this league was measured to serve, over
    #: the SEASON-SCHEDULE fixtures only. A change in either direction is a
    #: finding about the provider, not noise.
    #:
    #: Scoped to that one endpoint because `_parse_single_fixture` — the parser
    #: every `livescores` payload goes through — never populates `stats_id` for
    #: ANY sport; only `_parse_v1_season_schedule` does. Counting both endpoints
    #: together would have reported NHL as broken the first time a live contest
    #: had no season-schedule twin to dedupe against. MLB is simply the first
    #: sport whose season is in progress, so it is where that surfaced.
    stats_id_present: int = 0
    stats_id_absent: int = 0
    #: Set from the spec by the runner, so `summary()` can state the expectation
    #: next to the measurement instead of publishing a bare count.
    stats_id_coverage: str = STATS_ID_ON_NO_FIXTURE
    stats_id_measured: str = ""
    #: Live contests whose anchor field was blank and which the time-window rule
    #: recovered to a schedule contest. Not a link — a resolution of WHICH
    #: contest the live row is, after which it dedupes away like any other.
    live_anchor_recovered: int = 0
    #: Live contests whose anchor field was blank and which the rule REFUSED,
    #: because no schedule contest was inside the window or more than one was.
    #: Refusing is the point: the alternative is a confident wrong id.
    live_unkeyable: list[dict[str, Any]] = field(default_factory=list)
    sources_read: list[str] = field(default_factory=list)
    read_failures: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "sport_key": self.sport_key,
            "fixtures_read": self.fixtures_read,
            "rows_in_window": self.rows_in_window,
            "rows_measured": self.rows_measured,
            "stamped": self.stamped,
            "anchored_only": self.anchored_only,
            "already_linked": self.already_linked,
            "contradictions": len(self.contradictions),
            "polluted_column": len(self.polluted_column),
            "foreign_id_space": len(self.foreign_id_space),
            "ambiguous": len(self.ambiguous),
            "unmatched_fixtures": len(self.unmatched_fixtures),
            "unmatched_rows": len(self.unmatched_rows),
            "collisions": len(self.collisions),
            "write_refusals": len(self.write_refusals),
            "unknown_team_names": sorted(set(self.unknown_team_names)),
            "stats_id": {
                "present": self.stats_id_present,
                "absent": self.stats_id_absent,
                "expected": self.stats_id_coverage,
                "measured_when_set": self.stats_id_measured,
                "as_expected": self.stats_id_as_expected,
            },
            "live_anchor_recovered": self.live_anchor_recovered,
            "live_unkeyable": len(self.live_unkeyable),
            "sources_read": self.sources_read,
            "read_failures": self.read_failures,
        }

    @property
    def stats_id_as_expected(self) -> bool:
        """Did `stats_id` coverage match what this league was measured to serve?

        All-or-nothing for the two leagues measured as all-or-nothing: NHL serves
        it on 1404/1404 and NBA on 0/1206, so a single exception from either is a
        change worth a receipt and a "mostly" threshold would be a number nobody
        measured.

        MLB is the third case and it is deliberately NOT given a threshold
        either. Its expectation is *partial*, and what would falsify partial is
        the field becoming universal or vanishing — both of which are the
        provider changing its mind, and both of which this returns False for. A
        band around 87.2% would be inventing a tolerance to avoid stating one;
        the rate itself lives in `stats_id_measured`, where a reader can compare
        it against `present`/`absent` without this property pretending to.
        """
        if self.stats_id_coverage == STATS_ID_ON_EVERY_FIXTURE:
            return self.stats_id_absent == 0
        if self.stats_id_coverage == STATS_ID_ON_NO_FIXTURE:
            return self.stats_id_present == 0
        return self.stats_id_present > 0 and self.stats_id_absent > 0


def classify_fixture(
    fixture: StatPalFixture,
    pool: list[dict[str, Any]],
    anchor_space: Optional[set[str]] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Which of our rows, if any, is this StatPal contest?

    Pure: no session, no clock, no network. This is the whole decision the task
    makes, hoisted so it can be driven by real StatPal payloads and real event
    rows rather than by a mock that agrees with whatever it is told.

    Returns the verdict and the candidates it was reached on. `AMBIGUOUS` carries
    all of them, because "two rows matched" without saying which two is a count,
    and a receipt has to be actionable.

    Args:
        anchor_space: every id the authority endpoint published this pass. A
            column value outside it names nothing this endpoint can resolve, and
            is `FOREIGN_ID_SPACE` rather than a contradiction. Optional, and
            omitting it collapses that verdict back into `CONTRADICTION` — which
            is the honest degradation, because without the space there is no
            evidence to tell them apart. Never a digit count (D55).
    """
    if fixture.start_time is None:
        # No start is not a wide window, it is no window. Two teams meet two to
        # four times a season; matching on names alone would pair November with
        # March.
        return VERDICT_UNMATCHED, []

    matches = [
        c
        for c in pool
        if c.get("commence_time") is not None
        and abs(c["commence_time"] - fixture.start_time) <= MATCH_WINDOW
        and pair_matches(
            (fixture.home_team, fixture.away_team), (c["home"], c["away"])
        )
    ]
    if not matches:
        return VERDICT_UNMATCHED, []
    if len(matches) > 1:
        # Two of our rows for one contest is a duplicate, proven by something
        # better than a name window, and not this task's to resolve (D35, #2693).
        return VERDICT_AMBIGUOUS, matches

    row = matches[0]
    current = row.get("statpal_fixture_id")
    if current is None or not str(current).strip():
        return VERDICT_STAMP, matches
    if not is_statpal_contest_id(current):
        # #2963. The column says linked and holds a sentence. Not ours to repair.
        return VERDICT_POLLUTED, matches
    if str(current).strip() == str(fixture.fixture_id):
        # `statpal_sync` got here first and agrees with us. The column is right
        # and — measured 2026-09-04, 691 such rows and zero anchors — the anchor
        # is almost certainly missing, so this is work, not a skip.
        return VERDICT_ANCHOR_ONLY, matches
    if anchor_space is not None and str(current).strip() not in anchor_space:
        # The column names an id this endpoint never published. It is very
        # likely the SAME contest carrying its `livescores` number, which is a
        # namespace bug; calling it a contradiction would report it as a
        # matching bug and send it to the wrong owner.
        return VERDICT_FOREIGN_ID_SPACE, matches
    return VERDICT_CONTRADICTION, matches


def _fixture_receipt(fixture: StatPalFixture, **extra: Any) -> dict[str, Any]:
    """One fixture-side finding, with enough in it to act on.

    "1043639 did not match" is not a receipt. The two teams and the start are
    what a person needs to decide whether the miss is our gap or StatPal's.
    """
    return {
        "statpal_id": fixture.fixture_id,
        "statpal_stats_id": fixture.stats_id,
        "teams": [fixture.away_team, fixture.home_team],
        "start": fixture.start_time.isoformat() if fixture.start_time else None,
        "status": fixture.status,
        **extra,
    }


def _row_receipt(row: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """One of our rows that no StatPal contest claimed."""
    return {
        "event_id": row["id"],
        "teams": [row["away"], row["home"]],
        "commence_time": (
            row["commence_time"].isoformat() if row.get("commence_time") else None
        ),
        "status": row.get("status"),
        "statpal_fixture_id": row.get("statpal_fixture_id"),
        **extra,
    }


def live_anchor_id(spec: LeagueSpec, fixture: StatPalFixture) -> Optional[str]:
    """The anchor-space id this `livescores` contest carries, or None.

    Pure, and it reads a NAMED field per league rather than choosing between two
    numbers by their shape. On MLB both candidates are ten digits beginning
    `1329…` with overlapping ranges and no value in common, so shape is exactly
    the rule that would be confidently wrong (D55).
    """
    if spec.live_anchor_field == LIVE_ANCHOR_IS_ODDS_ID:
        return str(fixture.odds_id or "").strip() or None
    return str(fixture.fixture_id or "").strip() or None


def recover_live_anchor(
    fixture: StatPalFixture, schedule: list[StatPalFixture]
) -> tuple[Optional[str], str]:
    """Which scheduled contest is this live row, when its anchor field is blank?

    Both clubs in the same orientation, and first pitch within
    :data:`MATCH_WINDOW`. Unique or refuse. Returns `(anchor_id, reason)`, with
    the reason carried whether it resolved or not so a receipt never has to
    guess why.

    **Scored against ground truth rather than argued about.** The 13 MLB live
    rows that DO carry `oddsid` say which schedule row is correct, so a candidate
    rule can be measured on them. Sweeping the full 2026-09-04 census:

        key                correct   ambiguous   wrong
        (clubs, ±0.5h)          13           0       0
        (clubs, ±1h)            13           0       0
        (clubs, ±6h)            13           0       0
        (clubs, UTC day)         9           4       0

    The time key is exact at every tolerance tried; the calendar-day key is
    ambiguous on 4 of the 13 rows the anchor can already resolve. Worse, on the
    one row that is genuinely hard the day key does not merely flag it — it
    picks schedule row `354453`, which the doubleheader's FIRST game already
    holds by its own explicit `oddsid`. Two contests, one schedule row: gotcha
    #46's class. **Never key on a calendar day.**

    Applied to the three blanks, ±1h recovers Angels @ Pirates (0:05 apart) and
    Athletics @ Mariners (0:00) and REFUSES Detroit's nightcap, whose nearest
    same-pair schedule row is 3:05 away — the two endpoints disagree about that
    start by 3h05m and we do not know which is right. Coverage goes 13/16 to
    **15/16 with the 16th declared**, which beats 16/16 with one silently fused.

    Refusing costs nothing here, and that is worth stating so nobody widens the
    window to "fix" it: the refused contest is still read, from
    `season-schedule`, under its own id. What is lost is only the live VIEW of
    it, and what is gained is not writing a start time we cannot corroborate.
    """
    if fixture.start_time is None:
        return None, "live row carries no start time"
    matches = [
        s
        for s in schedule
        if s.start_time is not None
        and abs(s.start_time - fixture.start_time) <= MATCH_WINDOW
        and pair_matches(
            (fixture.home_team, fixture.away_team), (s.home_team, s.away_team)
        )
    ]
    if not matches:
        return None, f"no scheduled contest for this pair within {MATCH_WINDOW}"
    if len(matches) > 1:
        return None, (
            f"{len(matches)} scheduled contests for this pair within "
            f"{MATCH_WINDOW}: " + ", ".join(str(m.fixture_id) for m in matches)
        )
    return str(matches[0].fixture_id), f"recovered within {MATCH_WINDOW} on both clubs"


async def _read_fixtures(
    service, spec: LeagueSpec, run: StampRun
) -> tuple[list[StatPalFixture], set[str]]:
    """Every contest StatPal will tell us about right now, deduped by anchor id.

    Each source is read in its own try/except so one endpoint failing does not
    cost the other (gotcha #42) — but the failure is RECORDED, not swallowed. A
    run that read one of two endpoints and stamped what it could is a different
    fact from a run that read both, and only the receipt can say which happened.

    Returns the fixtures and the ANCHOR SPACE — every id `season-schedule`
    published this pass. A column value outside that set names nothing this
    endpoint can resolve, which `classify_fixture` reports as its own verdict
    rather than as a contradiction.
    """
    from app.services.statpal_api import StatPalUpstreamError

    seen: set[str] = set()
    fixtures: list[StatPalFixture] = []
    scheduled: list[StatPalFixture] = []
    anchor_space: set[str] = set()

    async def _read(label: str, coro) -> Optional[list[StatPalFixture]]:
        try:
            batch = await coro
        except StatPalUpstreamError as e:
            run.read_failures.append(f"{label}: {e}")
            logger.warning("StatPal %s %s unreadable: %s", spec.label, label, e)
            return None
        run.sources_read.append(label)
        return batch

    def _keep(fixture: StatPalFixture, anchor: str) -> None:
        if anchor in seen:
            return
        seen.add(anchor)
        # The anchor is what every downstream reader means by "this contest's
        # id": the dedup key, the column comparison and the anchor key itself.
        # Assigning it here is what keeps MLB's `oddsid` from having to be
        # remembered by four separate call sites.
        fixture.fixture_id = anchor
        fixtures.append(fixture)

    schedule_batch = await _read(
        "season-schedule", service.get_schedule_fixtures(spec.statpal_sport)
    )
    for f in schedule_batch or []:
        anchor = str(f.fixture_id or "").strip()
        if not anchor:
            continue
        anchor_space.add(anchor)
        scheduled.append(f)
        _keep(f, anchor)
        # Counted here and not over the merged list: `livescores` fixtures never
        # carry `stats_id` for any sport, so a combined count measures which
        # endpoints answered rather than what the provider serves.
        if f.stats_id and str(f.stats_id).strip():
            run.stats_id_present += 1
        else:
            run.stats_id_absent += 1

    # `livescores` is the only endpoint that knows a game while it is being
    # played, and a game that goes live unlinked is exactly the case the eventual
    # reader cares about. NBA opens 10/3 and NHL 9/19, so today it is legitimately
    # empty on both — which is a different fact from a failed read, and
    # `sources_read` is what tells them apart. MLB's season is in progress, so it
    # is the first sport for which this half does any work at all.
    live_batch = await _read(
        "livescores", service.get_live_fixtures(spec.statpal_sport)
    )
    for f in live_batch or []:
        anchor = live_anchor_id(spec, f)
        if anchor is None:
            recovered, reason = recover_live_anchor(f, scheduled)
            if recovered is None:
                run.live_unkeyable.append(_fixture_receipt(f, refused_because=reason))
                continue
            run.live_anchor_recovered += 1
            anchor = recovered
        _keep(f, anchor)

    run.fixtures_read = len(fixtures)
    return fixtures, anchor_space


def _measurement_population(
    wide: list[dict[str, Any]], write_pool: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The agreement row's population: the wide read, sharing the write pool's rows.

    Two reads of the same table hand back two sets of dicts, and the difference
    matters for exactly one field. The stamping loop mutates a candidate's
    `statpal_fixture_id` in place as it writes, and the agreement row is built
    afterwards so that a row this pass just stamped is published as anchored
    rather than as a hole it created itself. A second read taken BEFORE those
    writes cannot see them, so the overlapping rows are substituted for the write
    pool's own objects and the in-place mutation reaches the row as it always did.

    The union, not the wide read alone. `measurement_bounds` never narrows, so
    every write-pool row should already be in `wide` — but a population that
    silently drops a row it was asked to measure is the exact failure this whole
    change exists to remove, and the belt costs one pass over a few hundred dicts.
    """
    by_id = {r["id"]: r for r in write_pool}
    population = [by_id.get(r["id"], r) for r in wide]
    seen = {r["id"] for r in wide}
    population.extend(r for r in write_pool if r["id"] not in seen)
    return population


async def _candidates(
    session, spec: LeagueSpec, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(CANDIDATES),
            {
                "sport_key": spec.sport_key,
                "window_start": start,
                "window_end": end,
            },
        )
    ).fetchall()
    return [
        {
            "id": r[0],
            "home": r[1],
            "away": r[2],
            "commence_time": r[3],
            "statpal_fixture_id": r[4],
            "status": r[5],
        }
        for r in rows
    ]


def _claim_context(spec: LeagueSpec, fixture: StatPalFixture) -> dict[str, Any]:
    """What the anchor records about how this claim was reached.

    `statpal_stats_id` is in here and nowhere else that matters: NHL's second id
    is real and different from the one being anchored, and which of the two
    should anchor a game is program step 5's question. Carried where it is
    visible, never substituted for the id in the key.
    """
    return {
        "written_by": "stamp_v1_statpal_fixtures",
        "league": spec.label,
        "statpal_start": (
            fixture.start_time.isoformat() if fixture.start_time else None
        ),
        "statpal_stats_id": fixture.stats_id,
    }


async def _write_link(
    session, spec: LeagueSpec, fixture: StatPalFixture, candidate: dict
) -> str:
    """Write both shapes for one game. Returns the anchor outcome.

    The column is written FIRST and guarded by `statpal_fixture_id IS NULL`, so
    two concurrent passes cannot both claim it: the loser's UPDATE touches no row
    and it stops before writing an anchor for a link it did not make.
    """
    result = await session.execute(
        text(SET_FIXTURE_ID),
        {"event_id": candidate["id"], "fixture_id": fixture.fixture_id},
    )
    if not (result.rowcount or 0):
        return LOST_RACE

    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=statpal_anchor_key(
            fixture.fixture_id, statpal_id_space(spec.sport_key)
        ),
        claim_context=_claim_context(spec, fixture),
    )
    return written.outcome


async def _write_anchor_only(
    session, spec: LeagueSpec, fixture: StatPalFixture, candidate: dict
) -> str:
    """Complete the pair for a row whose column is already correct.

    No column write, so there is nothing to roll back on a refusal and nothing
    to race for: `record_anchor` is the whole transaction. This is the path that
    exists because `statpal_sync` writes the column for these two sports and has
    never written an anchor — 691 rows, 0 anchors, measured 2026-09-04 — and a
    column with no anchor reads as STALE on every lookup.
    """
    written = await record_anchor(
        session,
        event_id=candidate["id"],
        key=statpal_anchor_key(
            fixture.fixture_id, statpal_id_space(spec.sport_key)
        ),
        claim_context=_claim_context(spec, fixture) | {"column_was_already_set": True},
    )
    return written.outcome


def _note_unknown_names(run: StampRun, spec: LeagueSpec, *names: Optional[str]) -> None:
    for name in names:
        if name and not is_known_league_team(spec.sport_key, name):
            run.unknown_team_names.append(str(name))


async def _run_stamp_v1_statpal_fixtures(
    spec: LeagueSpec, *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    """One pass for one league. `apply=False` plans and writes nothing."""
    from app.tasks.base import get_task_session

    now = now or datetime.now(timezone.utc)
    run = StampRun(
        sport_key=spec.sport_key,
        stats_id_coverage=spec.stats_id_coverage,
        stats_id_measured=spec.stats_id_measured,
    )

    service = get_statpal_service()
    try:
        fixtures, anchor_space = await _read_fixtures(service, spec, run)
    finally:
        await service.close()

    if not fixtures:
        # Loud, not silent. Zero fixtures with no read failure means StatPal has
        # no games for this league at all — which for a SEASON schedule would be
        # remarkable. Zero WITH failures means we could not ask, and reporting
        # those identically is gotcha #53.
        logger.warning(
            "StatPal %s stamper read 0 fixtures (sources=%s, failures=%s)",
            spec.label,
            run.sources_read,
            run.read_failures,
        )
        # Zero yield is a ROW, not a skip (spec rule 6): a day the read failed
        # pauses the seven-day count, a day StatPal genuinely served nothing does
        # not, and the bus must tell them apart without reading the logs.
        return {
            **run.summary(),
            "agreement": build_agreement_row(
                sport_key=spec.sport_key,
                fixtures=[],
                rows=[],
                normalize=normalize_team,
                read_failures=run.read_failures,
                sources_read=run.sources_read,
                is_anchor_id=is_statpal_contest_id,
            ),
        }

    starts = [f.start_time for f in fixtures if f.start_time]
    window_start = (min(starts) if starts else now) - CANDIDATE_SLACK
    window_end = (max(starts) if starts else now) + CANDIDATE_SLACK
    #: WIDER than the write window, and read separately for that reason. Writing
    #: ids only makes sense where StatPal has a fixture to match, but MEASURING
    #: "of the games we list, does StatPal have them?" over StatPal's own span
    #: answers it only where StatPal already said yes (CERT-962).
    measure_start, measure_end = measurement_bounds(
        (window_start, window_end), now=now
    )

    async with get_task_session() as session:
        pool = await _candidates(session, spec, window_start, window_end)
        run.rows_in_window = len(pool)
        #: The measurement population, read in the SAME session as the write pool
        #: so both describe one moment (precedent D46). It is a superset of the
        #: write pool by construction — `measurement_bounds` never narrows — so
        #: the three sports whose local inventory already sits inside StatPal's
        #: span read exactly the rows they read before this existed.
        #:
        #: Kept separately rather than reusing `pool`, which is pruned as rows are
        #: claimed. The agreement row is measured over EVERY row in the population,
        #: including the ones this pass stamped — a denominator that shrinks as
        #: the task succeeds cannot be compared to yesterday's, and the seven-day
        #: count is exactly that comparison.
        all_rows = _measurement_population(
            await _candidates(session, spec, measure_start, measure_end), pool
        )
        run.rows_measured = len(all_rows)
        #: Which of our rows some contest claimed, so the leftovers can be
        #: reported as candidate phantoms. Claimed covers every verdict that
        #: names a row, not only the ones written: a contradicted or polluted row
        #: is accounted for, and calling it a phantom would be a second wrong
        #: answer on top of the first.
        claimed: set[int] = set()

        for fixture in fixtures:
            _note_unknown_names(run, spec, fixture.home_team, fixture.away_team)
            verdict, matches = classify_fixture(fixture, pool, anchor_space)

            if verdict == VERDICT_UNMATCHED:
                run.unmatched_fixtures.append(_fixture_receipt(fixture))
                continue

            for c in matches:
                claimed.add(c["id"])

            if verdict == VERDICT_AMBIGUOUS:
                run.ambiguous.append(
                    _fixture_receipt(
                        fixture,
                        candidates=[
                            {
                                "event_id": c["id"],
                                "teams": [c["away"], c["home"]],
                                "commence_time": c["commence_time"].isoformat(),
                                "statpal_fixture_id": c["statpal_fixture_id"],
                            }
                            for c in matches
                        ],
                    )
                )
                continue

            candidate = matches[0]

            if verdict == VERDICT_POLLUTED:
                # #2963. Receipted with the offending value and left alone: the
                # repair has a blast radius this task is not carrying.
                run.polluted_column.append(
                    _fixture_receipt(
                        fixture,
                        event_id=candidate["id"],
                        column_holds=candidate["statpal_fixture_id"],
                    )
                )
                continue

            if verdict == VERDICT_FOREIGN_ID_SPACE:
                # The column names an id `season-schedule` never published. Almost
                # certainly the right contest wearing its `livescores` number —
                # a namespace bug, not a matching one, and a different owner.
                #
                # Not repaired here even though the correct value is in hand:
                # overwriting a populated column across a whole sport is a data
                # write that owes a backup and a one-command restore (D51), and
                # the count in this receipt is exactly how that repair gets
                # sized. `_write_link`'s `IS NULL` guard would refuse it anyway.
                run.foreign_id_space.append(
                    _fixture_receipt(
                        fixture,
                        event_id=candidate["id"],
                        column_holds=candidate["statpal_fixture_id"],
                        anchor_should_be=fixture.fixture_id,
                    )
                )
                continue

            if verdict == VERDICT_CONTRADICTION:
                # The ingestion path chose a different contest for this row. One
                # of the two rules is wrong and this task does not get to say
                # which — overwriting would destroy the evidence that they
                # disagreed at all.
                run.contradictions.append(
                    _fixture_receipt(
                        fixture,
                        event_id=candidate["id"],
                        column_holds=candidate["statpal_fixture_id"],
                    )
                )
                continue

            if not apply:
                if verdict == VERDICT_ANCHOR_ONLY:
                    run.anchored_only += 1
                else:
                    run.stamped += 1
                continue

            try:
                if verdict == VERDICT_ANCHOR_ONLY:
                    outcome = await _write_anchor_only(
                        session, spec, fixture, candidate
                    )
                else:
                    outcome = await _write_link(session, spec, fixture, candidate)
            except Exception as e:  # one bad row never wipes the pass (#42)
                await session.rollback()
                logger.exception(
                    "StatPal %s stamp failed for contest %s -> event %s: %s",
                    spec.label, fixture.fixture_id, candidate["id"], e,
                )
                run.unmatched_fixtures.append(_fixture_receipt(fixture, error=str(e)))
                continue

            if outcome == LOST_RACE:
                run.already_linked += 1
                await session.rollback()
                continue

            if outcome not in COMMITTABLE_OUTCOMES:
                # A whitelist, not a blacklist. `STALE_INCUMBENT` and `NO_KEY`
                # would otherwise leave the column set with NO ANCHOR AT ALL — a
                # row whose column says linked while the anchor table says
                # nothing, which no reader can see.
                await session.rollback()
                run.write_refusals.append(
                    _fixture_receipt(
                        fixture, event_id=candidate["id"], outcome=outcome
                    )
                )
                if outcome == COLLISION:
                    run.collisions.append(
                        _fixture_receipt(
                            fixture, event_id=candidate["id"], outcome=outcome
                        )
                    )
                continue

            await session.commit()
            if verdict == VERDICT_ANCHOR_ONLY:
                # CONFIRMED here means the anchor already named this event, so
                # nothing was missing and nothing was written; WROTE means the
                # pair is complete for the first time. Counting them apart is
                # what makes "the backfill is done" a readable state.
                if outcome == WROTE:
                    run.anchored_only += 1
                else:
                    run.already_linked += 1
            else:
                run.stamped += 1
            # The agreement row is built after this loop and asks each row what
            # its column holds. A row this pass just stamped holds the id now,
            # and reading the pre-pass value would report the task's own success
            # as an unanchored game.
            candidate["statpal_fixture_id"] = fixture.fixture_id
            # The pool is per-pass, so a row claimed by this pass must not be
            # offered to the next contest — otherwise two contests can both
            # "match" it and the second silently loses the race instead of being
            # reported as the ambiguity it is.
            pool = [c for c in pool if c["id"] != candidate["id"]]
            if outcome != WROTE:
                logger.info(
                    "StatPal %s anchor for contest %s on event %s: %s",
                    spec.label, fixture.fixture_id, candidate["id"], outcome,
                )

        # The other direction. A row inside the window that no contest claimed is
        # a candidate phantom — or, for NHL today, one of the five rows whose
        # start time is our midnight-Eastern placeholder.
        for row in pool:
            if row["id"] in claimed:
                continue
            _note_unknown_names(run, spec, row.get("home"), row.get("away"))
            run.unmatched_rows.append(_row_receipt(row))

    agreement = build_agreement_row(
        sport_key=spec.sport_key,
        fixtures=[
            Side(
                ref=f.fixture_id,
                home=f.home_team,
                away=f.away_team,
                start=f.start_time,
                label=f.status,
            )
            for f in fixtures
        ],
        rows=[
            Side(
                ref=str(r["id"]),
                home=r["home"],
                away=r["away"],
                start=r["commence_time"],
                label=r.get("status"),
                # The same string as `label`, and deliberately passed twice:
                # `label` is receipts, `event_status` is consulted (#3226).
                event_status=r.get("status"),
                held_id=r.get("statpal_fixture_id"),
            )
            for r in all_rows
        ],
        normalize=normalize_team,
        read_failures=run.read_failures,
        sources_read=run.sources_read,
        window=(window_start, window_end),
        measurement_window=(measure_start, measure_end),
        is_anchor_id=is_statpal_contest_id,
    )

    # D50's seven-day count, folded into the durable ledger and attached to the
    # row as `agreement["streak"]`. Here rather than in the endpoint because
    # this pass is the only moment the day exists: the Redis metrics key holds
    # the LAST pass, so a day nobody folded is a day nobody can recover.
    agreement = await record_agreement_day(agreement, at=now, apply=apply)

    summary = run.summary()
    logger.info("StatPal %s stamper: %s", spec.label, summary)
    return {
        **summary,
        # The ledger row bus bucket M-R-AUTHORITY reads (D50's flip gate). Built
        # here rather than by a script because this pass already holds both sides
        # of the comparison at the same moment, and a script asking again an hour
        # later is comparing two different afternoons (precedent D46).
        "agreement": agreement,
        "contradiction_receipts": run.contradictions,
        "polluted_column_receipts": run.polluted_column,
        "foreign_id_space_receipts": run.foreign_id_space,
        "live_unkeyable_receipts": run.live_unkeyable,
        "ambiguous_receipts": run.ambiguous,
        "unmatched_fixture_receipts": run.unmatched_fixtures,
        "unmatched_row_receipts": run.unmatched_rows,
        "collision_receipts": run.collisions,
        "write_refusal_receipts": run.write_refusals,
    }


async def _run_stamp_nba_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    return await _run_stamp_v1_statpal_fixtures(NBA, apply=apply, now=now)


async def _run_stamp_nhl_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    return await _run_stamp_v1_statpal_fixtures(NHL, apply=apply, now=now)


async def _run_stamp_mlb_statpal_fixtures(
    *, apply: bool = True, now: Optional[datetime] = None
) -> dict[str, Any]:
    return await _run_stamp_v1_statpal_fixtures(MLB, apply=apply, now=now)
