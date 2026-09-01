"""Q506 — a FINAL nobody reported is not a FINAL. Guards for the D26 = (a) repair.

PILLAR: TRUTH. SHIP: a match that was never played stops showing as a finished
game with no score. 705 production rows, ~67 of them appearing a night.

WHAT THIS FILE IS DEFENDING, IN ORDER OF HOW BADLY IT WOULD GO WRONG
====================================================================

This repair's dangerous direction is not "fails to fix". It is **voids a real
game**. `status='voided'` removes a row from every surface allowlist, so a
false quarantine deletes a match off the site — and on 2026-09-01 the sport most
exposed to that is TENNIS, mid-US-Open, on the page Alex reviews with Lisa
tonight. So the guards are weighted accordingly:

1. `adapter_cannot_speak` HOLDS and does not void. Three separate guards, because
   three different mutants reach the same catastrophe: folding tennis into the
   adjudicable set, folding "cannot speak" into "no schedule of record", and
   letting a new `SPORT_LEAGUE_MAP` key default to adjudicable.
2. An unreachable authority HOLDS (gotcha #53 — `get_scoreboard` returns `[]` for
   an HTTP failure and an empty slate alike, and reading the first as absence
   voids a real game every time ESPN 500s). Guarded at BOTH levels: the pure
   decision, and the ESPN client method that has to make the distinction
   available at all.
3. An EMPTY slate HOLDS. An off-season league returns one every day.
4. Every write is a compare-and-set on the whole population predicate, so a row
   that acquires a score between the census and the write is `raced`, not
   clobbered.

THE GUARDS RUN THE RAIL. `repair()` is executed against a recording session and
a fake authority, and the assertions are on the SQL and the parameters it
actually issued — Q496's lesson, that a source assertion passes just as happily
on a dead call site. The pure-decision guards are separate and cheap, and they
are the ones that enumerate the ladder.
"""

from __future__ import annotations

import inspect
import re
from datetime import date, datetime, timezone

import pytest

from app.utils import fabricated_final as ff
from app.utils.event_completion import DERIVED_COMMENCE_SOURCES
from app.utils.sport_keys import SPORT_LEAGUE_MAP

import scripts.repair_fabricated_finals as rail


# ---------------------------------------------------------------------------
# Fixtures for the pure ladder
# ---------------------------------------------------------------------------

_UTC = timezone.utc


def _verdict(**kw) -> ff.AuthorityVerdict:
    kw.setdefault("reachable", True)
    return ff.AuthorityVerdict(**kw)


def _final(home=2, away=1, status="post", completed=None, state=None):
    return {
        "espn_id": "401",
        "status": status,
        "completed": completed,
        "state": state,
        "home": "Everton",
        "away": "Fulham",
        "home_score": home,
        "away_score": away,
        "start": datetime(2026, 8, 30, 14, 0, tzinfo=_UTC),
    }


# ---------------------------------------------------------------------------
# THE LADDER — one guard per rung, both arms where a rung has two
# ---------------------------------------------------------------------------


def test_a_sport_with_no_schedule_of_record_quarantines():
    """Rung 1 — 547 of the 705. esports has no ESPN endpoint and never will,
    so nothing can ever adjudicate the FINAL this row is wearing."""
    d, reason = ff.disposition_for("esports", _verdict(slate_size=0))
    assert (d, reason) == (ff.QUARANTINED, ff.NO_SCHEDULE_OF_RECORD)


def test_a_tournament_shaped_sport_is_HELD_and_never_voided():
    """🔴 Rung 2, and the one that must never regress.

    ESPN HAS a tennis endpoint, so `has_schedule_of_record` is True and a rail
    that stopped at rung 1 would fall through to "the fixture is not on the
    slate" and VOID it. But `_parse_event` reads `competitions[0]` — on the US
    Open payload that is ONE match out of 625 — and the tennis endpoint ignores
    `?dates=` entirely (measured 2026-09-01: atp/wta x 20260901/20260902 all
    returned byte-identical payloads). So the slate we could build for tennis is
    not a slate, and absence from it is not absence.

    46 tennis_atp + 28 tennis_wta production rows ride on this branch.
    """
    for sport in ("tennis_atp", "tennis_wta"):
        d, reason = ff.disposition_for(sport, _verdict(slate_size=0))
        assert (d, reason) == (ff.HELD, ff.ADAPTER_CANNOT_SPEAK), sport
        assert d != ff.QUARANTINED, f"{sport} was voided — real US Open matches"


def test_a_tournament_shaped_sport_is_still_held_when_the_slate_looks_full():
    """The same rung with the other arm of the input.

    A guard that only ever passes an EMPTY slate cannot tell "held because the
    adapter is blind" from "held because there was nothing to compare against".
    Rung 2 must fire before the slate is even consulted, so it has to hold on a
    populated slate too.
    """
    d, reason = ff.disposition_for(
        "golf_pga", _verdict(slate_size=140, fixture=None)
    )
    assert (d, reason) == (ff.HELD, ff.ADAPTER_CANNOT_SPEAK)


def test_an_unreachable_authority_holds():
    """Rung 3 — gotcha #53. An ESPN 500 must not void a real EPL fixture."""
    d, reason = ff.disposition_for("soccer_epl", _verdict(reachable=False))
    assert (d, reason) == (ff.HELD, ff.AUTHORITY_UNREACHABLE)


def test_an_empty_slate_holds_even_though_it_was_reachable():
    """Rung 4. A league in its off-season returns `{"events": []}` for every
    date, and so does a date format ESPN silently disliked. Absence is only ever
    asserted against a slate that demonstrably has fixtures in it."""
    d, reason = ff.disposition_for("soccer_epl", _verdict(slate_size=0))
    assert (d, reason) == (ff.HELD, ff.AUTHORITY_SLATE_EMPTY)


def test_absent_from_a_POPULATED_slate_with_NEITHER_side_on_it_quarantines():
    """Rung 5a — the directive's "the authority has no record of the event".

    The control for the two guards above: with the same `fixture=None`, a slate
    that HAS fixtures and does NOT mention either of our teams flips the verdict
    from held to quarantined. Without this arm, a mutant that holds
    unconditionally would pass every hold guard.

    The real 2026-09-01 instance: `'Spurs' v 'Raptors'` filed under
    `soccer_italy_serie_a`.
    """
    d, reason = ff.disposition_for(
        "soccer_epl", _verdict(slate_size=9, fixture=None, any_side_on_slate=False)
    )
    assert (d, reason) == (ff.QUARANTINED, ff.NOT_ON_THE_AUTHORITY_SLATE)


def test_a_name_matcher_miss_is_a_HOLD_and_not_an_absence():
    """🔴 Rung 5b, and the live replay is why it exists.

    `names_match` is deliberately suffix-only, so `"Brighton"` does not match
    `"Brighton & Hove Albion"` and `"Leipzig"` does not pair with
    `"Borussia Mönchengladbach"`. Both of those are REAL matches that were
    really played, and the first cut of this rail read the failed pairing as
    "the authority has no record" and VOIDED them off the site.

    If either of our two names is somewhere on the slate, the authority is
    plainly covering this competition today and OUR MATCHER is the thing that
    failed. That is not an absence and it must not be written.
    """
    d, reason = ff.disposition_for(
        "soccer_epl", _verdict(slate_size=9, fixture=None, any_side_on_slate=True)
    )
    assert (d, reason) == (ff.HELD, ff.PAIRING_UNRESOLVED)
    assert d != ff.QUARANTINED


def test_an_authority_final_repairs_from_its_score():
    """Rung 6 — the only branch that writes a number."""
    d, reason = ff.disposition_for(
        "soccer_epl", _verdict(slate_size=9, fixture=_final())
    )
    assert (d, reason) == (ff.REPAIRED_FINAL, ff.AUTHORITY_HAS_IT_FINAL)


@pytest.mark.parametrize("final_state", sorted(ff.AUTHORITY_FINAL_STATES))
def test_both_of_espns_mapped_finished_spellings_repair(final_state):
    """The FALLBACK path — a payload carrying neither `completed` nor `state`.
    `espn_helpers` tests `ee.status in ("post", "final")`; a rail that knew only
    one of them would silently UNSETTLE every row carrying the other."""
    d, _ = ff.disposition_for(
        "soccer_epl",
        _verdict(slate_size=9, fixture=_final(status=final_state)),
    )
    assert d == ff.REPAIRED_FINAL


def test_a_SOCCER_full_time_is_final_even_though_it_is_not_post():
    """🔴🔴 THE DEFECT THE LIVE REPLAY CAUGHT, AND THE UNIT GUARDS DID NOT.

    `_parse_event`'s ladder maps three `status.type.name` values and passes
    everything else through raw. Soccer never sends `STATUS_FINAL` — it sends
    `STATUS_FULL_TIME`, which maps to the string `"status_full_time"`.
    Measured 2026-09-01 across eng.1/esp.1/ger.1/ita.1/fra.1 for Aug 29-31:
    **42 of 42 finished matches**, not one of them `"post"`.

    So the first cut read every completed EPL/La Liga/Bundesliga/Serie A/
    Ligue 1 match as unfinished and would have UNSETTLED 66 REAL FINISHED GAMES
    back to `scheduled` — "Liverpool 2-2 Nottingham Forest, full time" as an
    upcoming fixture. The guards passed because they asserted the ladder, and
    the ladder was faithful to a vocabulary nobody had measured.
    """
    full_time = _final(status="status_full_time", completed=True, state="post")
    assert ff.authority_says_final(full_time) is True
    d, reason = ff.disposition_for("soccer_epl", _verdict(slate_size=9, fixture=full_time))
    assert (d, reason) == (ff.REPAIRED_FINAL, ff.AUTHORITY_HAS_IT_FINAL), (
        "a finished soccer match was read as unplayed — the rail would set a "
        "completed game back to `scheduled`"
    )


@pytest.mark.parametrize("name", [
    "status_full_time", "status_final_pen", "status_final_aet", "status_final_ot",
])
def test_espns_boolean_ALONE_settles_every_sport_specific_spelling(name):
    """The vocabulary is open-ended (penalties, extra time, overtime), which is
    exactly why the rail must not enumerate it. `type.completed` is a boolean
    and it is what ESPN itself keys on.

    `state` is deliberately left None here. With it set to "post" the boolean
    rung is untestable — the fallback catches the case and deleting the boolean
    check changes nothing (the mutation battery's M18 survived exactly that way).
    Each rung of an ordered fallback needs an input only that rung can answer.
    """
    assert ff.authority_says_final(_final(status=name, completed=True, state=None))
    assert not ff.authority_says_final(_final(status=name, completed=False, state=None))


def test_the_boolean_wins_when_it_CONTRADICTS_the_state():
    """Precedence, stated as a case rather than as an ordering in prose. ESPN's
    own flag is the authority; a stale `state` does not override it."""
    assert not ff.authority_says_final(
        _final(status="post", completed=False, state="post")
    )
    assert ff.authority_says_final(
        _final(status="scheduled", completed=True, state="pre")
    )


def test_the_state_field_is_the_second_signal_when_the_boolean_is_absent():
    """Ordered fallback, all three rungs exercised, so none of them is dead."""
    assert ff.authority_says_final({"status": "x", "completed": None, "state": "post"})
    assert not ff.authority_says_final({"status": "x", "completed": None, "state": "in"})
    assert ff.authority_says_final({"status": "post"})
    assert not ff.authority_says_final({"status": "scheduled"})


def test_a_swapped_orientation_holds_rather_than_writing_the_wrong_side():
    """Rung 7a. The pairing being present proves the fixture EXISTS, so this is
    not a quarantine — but it does not tell us which of OUR two names is home,
    and a score on the wrong side is the CAL-P002 corruption class."""
    d, reason = ff.disposition_for(
        "soccer_epl",
        _verdict(slate_size=9, fixture=_final(), orientation_swapped=True),
    )
    assert (d, reason) == (ff.HELD, ff.ORIENTATION_DISAGREES)


def test_a_final_with_no_score_holds():
    """Rung 7b. ESPN reporting FINAL with a null score is not a score."""
    d, reason = ff.disposition_for(
        "soccer_epl", _verdict(slate_size=9, fixture=_final(home=None))
    )
    assert (d, reason) == (ff.HELD, ff.AUTHORITY_FINAL_WITHOUT_A_SCORE)


@pytest.mark.parametrize("state", ["scheduled", "in", "postponed"])
def test_a_fixture_the_authority_has_not_finished_unsettles(state):
    """Rung 8. The settlement is the wrong field: clear it and take the real
    start. Same remedy `event_registry` applies to a staleness artifact."""
    d, reason = ff.disposition_for(
        "soccer_epl", _verdict(slate_size=9, fixture=_final(status=state))
    )
    assert (d, reason) == (ff.UNSETTLED, ff.AUTHORITY_HAS_IT_UNPLAYED)


def test_every_rung_reaches_a_named_disposition():
    """Ruling 054 — no unnamed bucket. Exercises the ladder end to end and
    asserts the return is always one of the four, never None or a bare string
    nobody counts."""
    cases = [
        ("esports", _verdict()),
        ("tennis_atp", _verdict()),
        ("soccer_epl", _verdict(reachable=False)),
        ("soccer_epl", _verdict(slate_size=0)),
        ("soccer_epl", _verdict(slate_size=9)),
        ("soccer_epl", _verdict(slate_size=9, fixture=_final())),
        ("soccer_epl", _verdict(slate_size=9, fixture=_final(status="in"))),
        (None, _verdict()),
    ]
    seen = set()
    for sport, v in cases:
        d, reason = ff.disposition_for(sport, v)
        assert d in ff.DISPOSITIONS, (sport, d)
        assert reason and isinstance(reason, str)
        seen.add(d)
    assert seen == set(ff.DISPOSITIONS), (
        f"the ladder never produced {set(ff.DISPOSITIONS) - seen} — a branch is "
        f"unreachable and these guards are not covering it"
    )


def test_an_unknown_sport_key_quarantines_rather_than_crashing():
    """A NULL `sport_id` on an event is possible (the candidate query LEFT JOINs
    `sports`). It must reach a verdict, and the right one: a row we cannot even
    name the sport of has no schedule of record by definition."""
    d, reason = ff.disposition_for(None, _verdict(slate_size=9))
    assert (d, reason) == (ff.QUARANTINED, ff.NO_SCHEDULE_OF_RECORD)


# ---------------------------------------------------------------------------
# THE PARTITION — exhaustive by guard, so a new sport cannot default wrong
# ---------------------------------------------------------------------------


def test_every_espn_sport_is_classified_as_fixture_or_tournament_shaped():
    """🔴 The build fails if a new `SPORT_LEAGUE_MAP` key lands in neither set.

    The alternative design — a tournament DENYLIST with "adjudicable" as the
    default — would silently mis-adjudicate the next tournament sport somebody
    adds, and mis-adjudication here means voiding real matches. This assertion
    is the thing that makes the positive list safe to maintain.
    """
    classified = ff.SCOREBOARD_ADJUDICABLE_SPORTS | ff.TOURNAMENT_SHAPED_SPORTS
    # ⚠️ This assertion is only worth anything while BOTH sets are written-out
    # literals. The first cut derived the adjudicable one as
    # `frozenset(SPORT_LEAGUE_MAP) - TOURNAMENT_SHAPED_SPORTS`, which made the
    # partition exhaustive BY CONSTRUCTION and let the mutation battery's M14 (a
    # fictional new ESPN sport) survive untouched. If someone re-derives either
    # set, this test goes vacuous silently — the reverse direction below is the
    # cheap tell, because a derived set can never contain a non-ESPN key.
    assert not (classified - set(SPORT_LEAGUE_MAP)), (
        f"{sorted(classified - set(SPORT_LEAGUE_MAP))} are classified here but "
        f"are not in SPORT_LEAGUE_MAP — the partition has drifted off its subject"
    )
    unclassified = set(SPORT_LEAGUE_MAP) - classified
    assert not unclassified, (
        f"{sorted(unclassified)} are in SPORT_LEAGUE_MAP but classified neither "
        f"adjudicable nor tournament-shaped. Decide which: an ESPN event whose "
        f"`competitions` list is a draw/field/card cannot be read by "
        f"`_parse_event`, which takes competitions[0]."
    )
    assert not (ff.SCOREBOARD_ADJUDICABLE_SPORTS & ff.TOURNAMENT_SHAPED_SPORTS)


def test_the_tournament_set_names_the_sports_that_actually_have_draws():
    """The specific regression alongside the class guard, which would also pass
    if someone emptied both sets into one."""
    assert {"tennis_atp", "tennis_wta", "golf_pga", "golf_lpga"} <= ff.TOURNAMENT_SHAPED_SPORTS
    assert "soccer_epl" in ff.SCOREBOARD_ADJUDICABLE_SPORTS
    assert "baseball_mlb" in ff.SCOREBOARD_ADJUDICABLE_SPORTS


def test_sports_with_no_espn_endpoint_are_the_ones_the_doctrine_names():
    """The doctrine table's bottom row, in code. These are 547 of the 705."""
    for sport in (
        "esports", "soccer_other", "americanfootball_other",
        "basketball_other", "motorsport_other", "lacrosse_other", "rugby_other",
    ):
        assert not ff.has_schedule_of_record(sport), sport
        assert not ff.adapter_can_speak_for(sport), sport


def test_the_derived_source_set_is_cert_690s_and_not_a_second_opinion():
    """The producer and the repair must not drift on what "derived" means. If a
    future derived provenance joins `DERIVED_COMMENCE_SOURCES`, this rail must
    pick it up without an edit."""
    assert ff.DERIVED_SOURCE_PARAM == sorted(DERIVED_COMMENCE_SOURCES)
    assert ff.DERIVED_SOURCE_PARAM == ["kalshi_ticker"]
    assert isinstance(ff.DERIVED_SOURCE_PARAM, list), (
        "asyncpg binds a list to text[]; a frozenset raises at execute time"
    )


# ---------------------------------------------------------------------------
# THE SQL — the population predicate, and compare-and-set on every write
# ---------------------------------------------------------------------------


def test_the_population_predicate_carries_all_four_conjuncts():
    p = ff.FABRICATED_FINAL_PREDICATE
    assert "commence_time_source = ANY(:derived_sources)" in p
    assert "status IN ('closed', 'completed')" in p
    assert "home_score IS NULL" in p and "away_score IS NULL" in p


@pytest.mark.parametrize(
    "sql_name",
    ["_WRITE_FINAL_SQL", "_WRITE_UNSETTLE_SQL", "_WRITE_VOID_SQL"],
)
def test_every_write_is_compare_and_set_on_the_population(sql_name):
    """🔴 gotcha #21 in the form that bites here.

    The census and the write are seconds apart and a poller runs every 15
    minutes. A row that acquires a real score in between must be skipped, not
    clobbered — so each UPDATE re-states the whole population predicate rather
    than trusting the id it was handed. The rail counts a zero rowcount as
    `raced`.
    """
    sql = getattr(rail, sql_name)
    assert "WHERE id = :event_id" in sql
    for conjunct in (
        "status IN ('closed', 'completed')",
        "home_score IS NULL",
        "away_score IS NULL",
        "commence_time_source = ANY(:derived_sources)",
    ):
        assert conjunct in sql, f"{sql_name} is missing `{conjunct}`"


def test_the_void_write_refuses_a_row_that_is_anchored_to_an_authority():
    """An `espn_id` means some authority named this row. Whatever else is wrong
    with it, it is not a phantom, and voiding it hides a real game behind a
    status no surface reads. 0/705 today — a guard on the rail's future, not a
    filter doing work now."""
    assert "espn_id IS NULL" in rail._WRITE_VOID_SQL
    assert "espn_id IS NULL" not in rail._WRITE_FINAL_SQL


def test_the_ticker_date_is_recovered_in_UTC_not_eastern():
    """The stand-in IS midnight UTC of the ticker date. An `America/New_York`
    cast — which the SIBLING rail correctly uses, because its timestamps are
    real ET game times — shifts every one of these to the previous day and asks
    ESPN the wrong question."""
    assert "AT TIME ZONE 'UTC'" in rail._TICKER_DATE_EXPR
    assert "New_York" not in rail._TICKER_DATE_EXPR
    for sql in (rail._DATES_SQL, rail._CANDIDATE_SQL):
        assert "AT TIME ZONE 'UTC'" in sql


def test_the_three_day_window_exists_and_is_symmetric():
    """A false "not on the slate" VOIDS a real game, so absence is only asserted
    after looking either side of a UTC-midnight artefact whose real fixture can
    fall on either day."""
    assert ff.AUTHORITY_DAY_OFFSETS == (-1, 0, 1)


# ---------------------------------------------------------------------------
# THE ESPN CLIENT — the zero has to be disambiguable at the source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_scoreboard_reachable_separates_a_failure_from_an_empty_slate():
    """🔴 gotcha #53 at the only level where it can be fixed.

    `get_scoreboard` cannot distinguish these and never could — that is fine for
    a poller and fatal for a rail that voids rows on absence. Both arms, because
    a method that returned `(False, [])` always would pass a one-armed guard.
    """
    from app.services.espn_api import ESPNAPIService

    svc = ESPNAPIService()

    async def _fail(url):
        return None

    async def _empty(url):
        return {"events": []}

    svc._get = _fail
    assert await svc.get_scoreboard_reachable("soccer_epl", "20260830") == (False, [])

    svc._get = _empty
    reachable, events = await svc.get_scoreboard_reachable("soccer_epl", "20260830")
    assert reachable is True and events == []

    # ...and the legacy method still collapses both, which is why the repair
    # must not use it.
    svc._get = _fail
    assert await svc.get_scoreboard("soccer_epl", "20260830") == []
    svc._get = _empty
    assert await svc.get_scoreboard("soccer_epl", "20260830") == []


def test_parse_event_carries_espns_own_completed_and_state():
    """The two fields the full-time fix stands on have to survive the PARSE, not
    just exist in the payload. Shaped exactly like ESPN's soccer scoreboard as
    measured 2026-09-01 — `STATUS_FULL_TIME`, `completed: true`, `state: post` —
    so the assertion is that the mapped `status` is NOT "post" and the rail is
    still told the match is over."""
    from app.services.espn_api import ESPNAPIService

    parsed = ESPNAPIService()._parse_event({
        "id": "401879314",
        "name": "Liverpool v Nottingham Forest",
        "date": "2026-08-29T11:30Z",
        "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True,
                            "state": "post", "detail": "FT"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "Liverpool"}},
            {"homeAway": "away", "score": "2",
             "team": {"displayName": "Nottingham Forest"}},
        ]}],
    })
    assert parsed is not None
    assert parsed.status == "status_full_time", (
        "the mapped status changed — if it is now 'post', re-check whether this "
        "guard is still testing the gap it was written for"
    )
    assert parsed.completed is True
    assert parsed.state == "post"
    assert ff.authority_says_final({
        "status": parsed.status, "completed": parsed.completed,
        "state": parsed.state,
    })


@pytest.mark.asyncio
async def test_an_unmapped_sport_is_unreachable_not_empty():
    """`esports` has no ESPN path at all. The client must say so with
    `reachable=False` rather than handing back a clean empty slate that reads as
    "ESPN has no such fixture"."""
    from app.services.espn_api import ESPNAPIService

    assert await ESPNAPIService().get_scoreboard_reachable("esports", "20260830") == (
        False,
        [],
    )


# ---------------------------------------------------------------------------
# THE RAIL, RUN — recording session + fake authority
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, event_id, sport_key, home, away, ticker_date,
                 status="closed", commence=None, espn_id=None):
        self.event_id = event_id
        self.sport_key = sport_key
        self.ev_status = status
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence or datetime(2026, 8, 30, 0, 0, tzinfo=_UTC)
        self.completed_at = datetime(2026, 8, 30, 6, 0, tzinfo=_UTC)
        self.espn_id = espn_id
        self.ticker_date = ticker_date


class _DateRow:
    def __init__(self, ticker_date, n, sports):
        self.ticker_date = ticker_date
        self.n = n
        self.sports = sports


class _Result:
    def __init__(self, rows=(), scalar=0, rowcount=1):
        self._rows = list(rows)
        self._scalar = scalar
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _RecordingSession:
    """Dispatches on TABLE NAME first, then on statement shape.

    Dispatch order matters: a `SELECT COUNT(*) AS n FROM events` and the date
    census both mention `events`, and a branch that matched on `COUNT(*)` alone
    would feed the population count into the date loop. That exact trap is
    banked from the sibling rail's harness.
    """

    def __init__(self, *, dates, candidates, population=0, rowcount=1):
        self.dates = dates
        self.candidates = candidates
        self.population = population
        self.rowcount = rowcount
        self.statements: list[tuple[str, dict]] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, dict(params or {})))
        if sql.strip().upper().startswith("UPDATE"):
            return _Result(rowcount=self.rowcount)
        if "win_prob_snapshots" in sql:
            return _Result(rows=[])
        if "COUNT(*) AS n" in sql and "GROUP BY" not in sql:
            return _Result(scalar=self.population)
        if "AS ticker_date" in sql and "GROUP BY" in sql:
            return _Result(rows=self.dates)
        if "AS event_id" in sql:
            dates = set((params or {}).get("dates") or [])
            return _Result(rows=[c for c in self.candidates if c.ticker_date in dates])
        raise AssertionError(f"unexpected SQL: {sql[:200]}")

    async def commit(self):
        self.commits += 1


class _FakeTeam:
    def __init__(self, name):
        self.name = name


class _FakeEvent:
    def __init__(self, espn_id, status, home, away, hs, as_, start,
                 completed=None, state=None):
        self.espn_id = espn_id
        self.status = status
        self.home_team = _FakeTeam(home)
        self.away_team = _FakeTeam(away)
        self.home_score = hs
        self.away_score = as_
        self.date = start
        self.completed = completed
        self.state = state


class _FakeESPN:
    """Records every scoreboard call, so the call BUDGET is observable."""

    def __init__(self, by_date=None, reachable=True):
        self.by_date = by_date or {}
        self.reachable = reachable
        self.calls: list[tuple[str, str]] = []

    async def get_scoreboard_reachable(self, sport_key, date_str):
        self.calls.append((sport_key, date_str))
        if not self.reachable:
            return (False, [])
        return (True, list(self.by_date.get(date_str, [])))

    async def get_scoreboard(self, sport_key, date_str=None):  # pragma: no cover
        raise AssertionError(
            "the rail called get_scoreboard, which cannot tell a failed request "
            "from an empty slate — it must use get_scoreboard_reachable"
        )


async def _run(monkeypatch, session, espn, **kw):
    monkeypatch.setattr(
        "app.services.espn_api.get_espn_service", lambda: espn, raising=True
    )
    return await rail.repair(session, kw.pop("apply", False), **kw)


_D = date(2026, 8, 30)
_DSTR = "20260830"


@pytest.mark.asyncio
async def test_a_dry_run_issues_no_update_and_never_commits(monkeypatch):
    """The default is a census. A rail whose dry run wrote would be discovered
    in production, which is the only place this population lives."""
    s = _RecordingSession(
        dates=[_DateRow(_D, 2, 1)],
        candidates=[_Row(1, "esports", "Team A", "Team B", _D),
                    _Row(2, "esports", "Team C", "Team D", _D)],
        population=2,
    )
    out = await _run(monkeypatch, s, _FakeESPN(), apply=False)

    assert not [sql for sql, _ in s.statements if sql.strip().upper().startswith("UPDATE")]
    assert s.commits == 0
    assert out["dispositions"][ff.QUARANTINED] == 2
    assert out["written"] == {ff.REPAIRED_FINAL: 0, ff.UNSETTLED: 0, ff.QUARANTINED: 0}
    assert out["applied"] is False


@pytest.mark.asyncio
async def test_a_no_authority_sport_costs_zero_espn_calls(monkeypatch):
    """547 of the 705 are decided from the sport key alone. Spending three
    scoreboard calls per esports date would burn the whole budget adjudicating
    rows no adapter can adjudicate, and the page would never advance."""
    espn = _FakeESPN()
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(1, "esports", "Team A", "Team B", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=False)
    assert espn.calls == []
    assert out["authority_calls"] == 0


@pytest.mark.asyncio
async def test_apply_voids_a_no_authority_row_and_commits(monkeypatch):
    espn = _FakeESPN()
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(7, "soccer_other", "Team A", "Team B", _D)],
        population=1,
    )
    out = await _run(monkeypatch, s, espn, apply=True)

    updates = [(sql, p) for sql, p in s.statements
               if sql.strip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    sql, params = updates[0]
    assert f"status = '{ff.VOID_STATUS}'" in sql
    assert params["event_id"] == 7
    assert params["derived_sources"] == ["kalshi_ticker"]
    assert s.commits == 1
    assert out["written"][ff.QUARANTINED] == 1
    assert out["raced"] == 0


@pytest.mark.asyncio
async def test_apply_writes_the_authoritys_score_state_and_real_start(monkeypatch):
    """🔴 The one branch that writes a number, run end to end.

    Asserted on the PARAMETERS, not on the SQL text: the defect this rail exists
    to remove is a wrong value, and a guard that only checked the statement
    shape would pass on a rail that wrote our own stand-in back.
    """
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Everton", "Fulham", 3, 1, start)]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
        population=1,
    )
    out = await _run(monkeypatch, s, espn, apply=True)

    sql, params = [(a, b) for a, b in s.statements
                   if a.strip().upper().startswith("UPDATE")][0]
    assert params["home_score"] == 3 and params["away_score"] == 1
    assert params["commence_time"] == start, (
        "the row kept its midnight stand-in — the repair has to take the "
        "authority's real start, which is what lets CERT-690's clock run again"
    )
    assert f"status = '{ff.FINAL_STATUS}'" in sql
    assert "commence_time_source = 'espn'" in sql
    assert out["written"][ff.REPAIRED_FINAL] == 1


@pytest.mark.asyncio
async def test_completed_at_is_derived_and_is_never_the_wall_clock(monkeypatch):
    """gotcha #22. No snapshot exists for this cohort, so the derivation returns
    None — a visible gap the next repair can fill, rather than a plausible
    `now()` nothing will ever question. It is WRITTEN as None rather than left
    alone, because the stale value was computed from the stand-in and would
    invert gotcha #46 the moment the start moves forward."""
    before = datetime.now(_UTC)
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Everton", "Fulham", 3, 1, start)]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    await _run(monkeypatch, s, espn, apply=True)

    params = [b for a, b in s.statements if a.strip().upper().startswith("UPDATE")][0]
    assert params["completed_at"] is None
    assert not isinstance(params["completed_at"], datetime) or (
        params["completed_at"] < before
    )


@pytest.mark.asyncio
async def test_a_race_is_counted_and_not_reported_as_a_write(monkeypatch):
    """rowcount 0 means the compare-and-set refused: the row changed under us.
    A rail that reported it as written would tell the operator the population
    had drained when it had not."""
    espn = _FakeESPN()
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(7, "esports", "A", "B", _D)],
        rowcount=0,
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    assert out["raced"] == 1
    assert out["written"][ff.QUARANTINED] == 0


@pytest.mark.asyncio
async def test_an_espn_outage_holds_every_row_and_writes_nothing(monkeypatch):
    """🔴 The end-to-end form of gotcha #53. `reachable=False` on every call, a
    real EPL fixture in the population, and the rail must emit ZERO updates."""
    espn = _FakeESPN(reachable=False)
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)

    assert not [a for a, _ in s.statements if a.strip().upper().startswith("UPDATE")]
    assert out["dispositions"][ff.HELD] == 1
    assert out["reasons"][ff.AUTHORITY_UNREACHABLE] == 1


@pytest.mark.asyncio
async def test_a_tennis_row_survives_a_full_apply_untouched(monkeypatch):
    """🔴 THE REGRESSION THAT MATTERS. Run the whole rail, apply=True, over a
    US Open row, and assert the events table is not written at all."""
    espn = _FakeESPN()
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(11, "tennis_atp", "C Alcaraz", "J Sinner", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)

    assert not [a for a, _ in s.statements if a.strip().upper().startswith("UPDATE")]
    assert espn.calls == [], "the adapter cannot read a draw; it must not try"
    assert out["dispositions"][ff.HELD] == 1
    assert out["reasons"][ff.ADAPTER_CANNOT_SPEAK] == 1


@pytest.mark.asyncio
async def test_the_authority_is_asked_for_three_days_around_the_ticker_date(monkeypatch):
    """The stand-in is midnight UTC; ESPN's day boundary is not. Asking only the
    ticker date would report a real Friday-night fixture as absent and void it."""
    espn = _FakeESPN()
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    await _run(monkeypatch, s, espn, apply=False)
    assert [d for _, d in espn.calls] == ["20260829", "20260830", "20260831"]


@pytest.mark.asyncio
async def test_a_fixture_found_on_the_adjacent_day_is_repaired_not_voided(monkeypatch):
    """The three-day window has to actually be USED, not merely fetched. A rail
    that unioned the days but matched only within the ticker date would pass the
    call-count guard above and still void the row."""
    start = datetime(2026, 8, 29, 19, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        "20260829": [_FakeEvent("401", "post", "Everton", "Fulham", 2, 0, start)],
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    assert out["dispositions"][ff.REPAIRED_FINAL] == 1
    assert out["dispositions"][ff.QUARANTINED] == 0


@pytest.mark.asyncio
async def test_a_one_sided_name_match_is_not_a_match(monkeypatch):
    """"Everton vs Fulham" must not match "Everton vs Brentford". On this rail
    a wrong match writes another game's final onto a real row — the
    `espn_id_drifted` lesson from CAL-P002, reached by a different door.

    And it must not VOID it either: "Everton" IS on the slate, so the authority
    covers this competition today and the pairing is unresolved, not absent.
    Both halves asserted, because a rail that voided here and a rail that scored
    here are two different disasters and only one of them is loud.
    """
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Everton", "Brentford", 4, 0, start,
                           completed=True, state="post")]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    assert out["dispositions"][ff.REPAIRED_FINAL] == 0
    assert out["dispositions"][ff.QUARANTINED] == 0
    assert out["reasons"][ff.PAIRING_UNRESOLVED] == 1
    assert not [a for a, _ in s.statements if a.strip().upper().startswith("UPDATE")]


@pytest.mark.asyncio
async def test_a_fixture_the_slate_has_never_heard_of_is_voided(monkeypatch):
    """The control for the guard above, and the real 2026-09-01 instance:
    `'Spurs' v 'Raptors'` filed under a Serie A row. Neither name is anywhere on
    the slate, so this is a genuine absence and the phantom final is voided."""
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Napoli", "Como", 1, 2, start,
                           completed=True, state="post")]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_italy_serie_a", "Spurs", "Raptors", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    assert out["dispositions"][ff.QUARANTINED] == 1
    assert out["reasons"][ff.NOT_ON_THE_AUTHORITY_SLATE] == 1
    assert f"status = '{ff.VOID_STATUS}'" in [
        a for a, _ in s.statements if a.strip().upper().startswith("UPDATE")
    ][0]


@pytest.mark.asyncio
async def test_a_finished_SOCCER_match_is_repaired_end_to_end(monkeypatch):
    """🔴 The full-time defect, run through the whole rail rather than the pure
    ladder. `status='status_full_time'` is what ESPN actually sends and what the
    parse actually produces; the rail must write the score, not un-settle it."""
    start = datetime(2026, 8, 29, 11, 30, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401879314", "status_full_time", "Liverpool",
                           "Nottingham Forest", 2, 2, start,
                           completed=True, state="post")]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Liverpool", "Nottingham Forest", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    sql, params = [(a, b) for a, b in s.statements
                   if a.strip().upper().startswith("UPDATE")][0]
    assert out["dispositions"][ff.REPAIRED_FINAL] == 1
    assert out["dispositions"][ff.UNSETTLED] == 0, (
        "a full-time match was set back to `scheduled`"
    )
    assert params["home_score"] == 2 and params["away_score"] == 2
    assert f"status = '{ff.FINAL_STATUS}'" in sql


@pytest.mark.asyncio
async def test_a_swapped_pairing_is_held_and_no_score_is_written(monkeypatch):
    """End to end: the fixture exists (so not quarantined) and no score is
    written (so not corrupted)."""
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Fulham", "Everton", 1, 3, start)]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 1, 1)],
        candidates=[_Row(9, "soccer_epl", "Everton", "Fulham", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=True)
    assert not [a for a, _ in s.statements if a.strip().upper().startswith("UPDATE")]
    assert out["reasons"][ff.ORIENTATION_DISAGREES] == 1


@pytest.mark.asyncio
async def test_the_page_is_bounded_by_dates_and_hands_back_a_date_cursor(monkeypatch):
    """CAL-P058: this repair removes rows from its own population, so the cursor
    cannot be an offset. `next_since` is the first date NOT processed."""
    dates = [_DateRow(date(2026, 8, 20 + i), 1, 1) for i in range(8)]
    cands = [_Row(100 + i, "esports", "A", "B", date(2026, 8, 20 + i))
             for i in range(8)]
    s = _RecordingSession(dates=dates, candidates=cands)
    out = await _run(monkeypatch, s, _FakeESPN(), apply=False, limit=3)

    assert out["dates_selected"] == ["2026-08-20", "2026-08-21", "2026-08-22"]
    assert out["next_since"] == "2026-08-23"
    assert out["dates_remaining"] == 5


@pytest.mark.asyncio
async def test_the_espn_call_budget_stops_the_page_before_the_router_wall(monkeypatch):
    """CAL-P002B: `limit` bounding rows rather than CALLS is what H12'd the
    sibling rail at 30s. Three calls per adjudicable (sport, date), so the page
    must stop on the budget even when the date limit is nowhere near."""
    n = rail.MAX_AUTHORITY_CALLS  # more dates than the budget can pay for
    dates = [_DateRow(date(2026, 8, 1) .replace(day=1 + i), 1, 1) for i in range(n)]
    cands = [_Row(200 + i, "soccer_epl", "Everton", "Fulham",
                  date(2026, 8, 1).replace(day=1 + i)) for i in range(n)]
    s = _RecordingSession(dates=dates, candidates=cands)
    out = await _run(monkeypatch, s, _FakeESPN(), apply=False, limit=n)

    assert out["authority_calls"] <= rail.MAX_AUTHORITY_CALLS
    assert out["next_since"] is not None, (
        "the page stopped on the budget but handed back no cursor — the rest of "
        "the population is unreachable"
    )
    assert len(out["dates_selected"]) < n


@pytest.mark.asyncio
async def test_the_budget_also_stops_a_SINGLE_date_that_is_too_expensive(monkeypatch):
    """🔴 The second half of the budget, and the mutation battery is why it is
    here.

    Page selection admits the FIRST date unconditionally — it has to, or a date
    whose cost exceeds the whole budget would never be processed and the cursor
    would never advance past it. So the budget needs a SECOND check inside the
    per-sport loop, and the first cut of these guards never reached it: every
    budget case they built had one sport per date, so selection always stopped
    first and deleting the inner check changed nothing (battery M13 survived).

    One date, twenty adjudicable sports = 60 calls wanted against a 30 budget.
    The rail must stop mid-date, spend no more than the budget, and return a
    cursor pointing back AT this date so the sports it did not reach are reached
    next time.
    """
    sports = sorted(ff.SCOREBOARD_ADJUDICABLE_SPORTS)[:20]
    assert len(sports) * len(ff.AUTHORITY_DAY_OFFSETS) > rail.MAX_AUTHORITY_CALLS
    cands = [_Row(300 + i, sp, "Everton", "Fulham", _D) for i, sp in enumerate(sports)]
    s = _RecordingSession(dates=[_DateRow(_D, len(cands), len(sports))],
                          candidates=cands)
    espn = _FakeESPN()
    out = await _run(monkeypatch, s, espn, apply=False, limit=1)

    assert out["dates_selected"] == [str(_D)], "the only date was not admitted"
    assert len(espn.calls) <= rail.MAX_AUTHORITY_CALLS, (
        f"spent {len(espn.calls)} scoreboard calls against a budget of "
        f"{rail.MAX_AUTHORITY_CALLS} — at ~0.5s each this is the CAL-P002B H12"
    )
    assert out["authority_calls"] == len(espn.calls)
    assert out["next_since"] == str(_D), (
        "the page stopped mid-date and pointed the cursor past it — the sports "
        "it never reached would be skipped forever"
    )
    # ...and it stopped because of the budget, not because it did nothing.
    assert len(espn.calls) > 0
    assert sum(out["dispositions"].values()) < len(cands)


@pytest.mark.asyncio
async def test_every_candidate_row_is_accounted_for_in_the_counts(monkeypatch):
    """Ruling 054 as arithmetic: the disposition counts must sum to the rows
    scanned. A branch that `continue`d past a row would leave it in no bucket
    and the operator would read a short census as a drained one."""
    espn = _FakeESPN(by_date={_DSTR: [
        _FakeEvent("401", "post", "Everton", "Fulham", 3, 1,
                   datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)),
    ]})
    cands = [
        _Row(1, "esports", "A", "B", _D),
        _Row(2, "tennis_atp", "C", "D", _D),
        _Row(3, "soccer_epl", "Everton", "Fulham", _D),
        _Row(4, "soccer_epl", "Arsenal", "Chelsea", _D),
    ]
    s = _RecordingSession(dates=[_DateRow(_D, 4, 3)], candidates=cands)
    out = await _run(monkeypatch, s, espn, apply=False)

    assert sum(out["dispositions"].values()) == len(cands)
    assert sum(out["reasons"].values()) == len(cands)
    assert len(out["ledger"]) == len(cands)
    assert out["dispositions"] == {
        ff.REPAIRED_FINAL: 1,   # Everton v Fulham, final
        ff.UNSETTLED: 0,
        ff.QUARANTINED: 2,      # esports (no authority) + Arsenal (absent)
        ff.HELD: 1,             # tennis
    }


@pytest.mark.asyncio
async def test_the_leagues_with_no_schedule_of_record_are_NAMED(monkeypatch):
    """Doctrine rule 8 makes chasing a new source a RULE, not a judgement — but
    only if the rail says which leagues. A bare quarantine count hides the
    thing the next ship needs."""
    s = _RecordingSession(
        dates=[_DateRow(_D, 3, 2)],
        candidates=[_Row(1, "esports", "A", "B", _D),
                    _Row(2, "esports", "C", "D", _D),
                    _Row(3, "soccer_other", "E", "F", _D)],
    )
    out = await _run(monkeypatch, s, _FakeESPN(), apply=False)
    assert out["no_schedule_of_record_leagues"] == {"esports": 2, "soccer_other": 1}


@pytest.mark.asyncio
async def test_a_quarantine_against_a_real_slate_is_listed_by_name(monkeypatch):
    """The 547 no-authority voids and the handful of genuine absences are two
    different claims, and only the second is checkable by hand. Reporting them
    as one number is how a name-matcher regression would hide: it would show up
    as the big count moving a little.

    On the real population this list is NINE rows, eight of which turn out to be
    a second-tier fixture filed under the top-flight key.
    """
    start = datetime(2026, 8, 30, 14, 0, tzinfo=_UTC)
    espn = _FakeESPN(by_date={
        _DSTR: [_FakeEvent("401", "post", "Napoli", "Como", 1, 2, start,
                           completed=True, state="post")]
    })
    s = _RecordingSession(
        dates=[_DateRow(_D, 2, 2)],
        candidates=[_Row(1, "esports", "A", "B", _D),
                    _Row(2, "soccer_italy_serie_a", "Spurs", "Raptors", _D)],
    )
    out = await _run(monkeypatch, s, espn, apply=False)

    assert out["dispositions"][ff.QUARANTINED] == 2
    listed = out["absent_from_a_populated_slate"]
    assert [e["event_id"] for e in listed] == [2], (
        "the no-schedule-of-record void was folded into the absent list, or the "
        "genuine absence was not named"
    )
    assert listed[0]["matchup"] == "Spurs v Raptors"
    assert listed[0]["slate_size"] == 1


# ---------------------------------------------------------------------------
# REGISTRATION — a repair nobody can call is not shipped
# ---------------------------------------------------------------------------


def test_the_repair_is_registered_and_the_dispatcher_can_forward_its_params():
    import app.routes.admin_repairs as mod

    assert "fabricated-finals" in mod._REPAIRS
    module_path, fn_name = mod._REPAIRS["fabricated-finals"]
    assert (module_path, fn_name) == ("scripts.repair_fabricated_finals", "repair")

    accepted = set(inspect.signature(rail.repair).parameters)
    declared = set(inspect.signature(mod.run_repair).parameters)
    for p in ("limit", "sport", "since"):
        assert p in accepted, f"repair() does not accept {p}"
        assert p in declared, f"run_repair() cannot forward {p}"


def test_the_registration_comment_documents_only_forwardable_params():
    """The Q495 prose defect, scoped to this block. The file-wide guard lives in
    `test_repair_polymarket_sport_category_q496.py`; this one fails in the file
    a reader of THIS repair is looking at."""
    import app.routes.admin_repairs as mod

    src = inspect.getsource(mod)
    start = src.index('"fabricated-finals": (')
    block = src[max(0, start - 2200):start]
    documented = set(re.findall(r"[?&]([a-zA-Z_][a-zA-Z0-9_]*)=", block))
    assert documented, "the registration comment documents no params at all"
    assert documented <= set(inspect.signature(mod.run_repair).parameters)


def test_the_module_docstring_names_the_ruling_and_the_ship():
    """These rails are read by whoever is holding the pager at 2am. Q506's
    subject is a data write over 705 production rows and the reason it is
    allowed to happen is one Alex ruling."""
    doc = rail.__doc__ or ""
    assert "D26" in doc
    assert "authority" in doc.lower()
    assert len(doc) > 2000, "the argument for a 705-row production write is short"
