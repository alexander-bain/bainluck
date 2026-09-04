"""Q476 — a league page's Recent Results stops printing a game twice.

THE SPECIMEN, measured on production 2026-08-31 via `GET /api/leagues/soccer_epl`.
Eight "recent results" for FOUR games; four of the cards had no result in them:

    15290890  Manchester United v Ipswich Town  15:30Z  espn           5-2
    15298940  Manchester United v Ipswich Town  00:00Z  kalshi_ticker  -
    15290898  Sunderland v Fulham               13:00Z  espn           1-0
    15298364  Sunderland v Fulham               00:00Z  kalshi_ticker  -
    15299046  Sunderland AFC v Fulham FC        00:00Z  kalshi_ticker  -
    15290743  Chelsea v Brighton and Hove Albion 13:00Z espn           4-3
    15297751  Chelsea FC v Brighton & Hove Albion 00:00Z kalshi_ticker -

`Sunderland v Fulham` printed three times, once under a different name for the
same two clubs — so a name key does not collapse these, and a time window would
have to be wide enough to swallow real fixtures.

WHAT DOES collapse them is Kalshi's own fixture token, carried by every series
that prices the match AND by a market already sitting on the real row:

    26AUG30MUNIPS  -> 15290890 (espn, 5-2)  AND  15298940 (ticker, no score)
    26AUG30SUNFUL  -> 15290898 (espn, 1-0)  AND  15298364, 15299046
    26AUG30CFCBRI  -> 15290743 (espn, 4-3)  AND  15297751

Ruling 048 arm A: a shared provider id, read out of the provider's ticker, not
guessed from names and a clock. Census over every league, same day: **1,484
tokens split across 4,354 event rows — 2,870 excess rows in 30 days.**

THE SAFETY INVARIANT these tests exist to pin: a SCHEDULE-DERIVED event is never
tagged. Hiding a real game is the failure direction that leaves no trace on the
page, and it is unreachable while that holds — a real game has a schedule-derived
row and that row can only ever be the survivor.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import aliased

from app.models.models import Event
from app.routes.league_futures import (
    recent_results_query,
    upcoming_games_query,
)
from app.services.anchor_channel import (
    DUPLICATE_TAG_PREFIX,
    not_a_proven_duplicate,
)
from app.tasks.prediction_market_matching import (
    _drain_kalshi_token_twins,
)
from app.utils.prediction_market_matching import (
    kalshi_game_twin_key,
    kalshi_match_segment_key,
)

NOW = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)

#: The real Kalshi series pricing ONE Premier League fixture, copied from
#: production `futures_markets.external_id` on 2026-08-31.
SUNFUL_SIBLINGS = (
    "KXEPLBTTS-26AUG30SUNFUL",
    "KXEPLFTTS-26AUG30SUNFUL",
    "KXEPLSCORE-26AUG30SUNFUL",
    "KXEPL1H-26AUG30SUNFUL",
    "KXEPL1HTOTAL-26AUG30SUNFUL",
    "KXEPL1HSPREAD-26AUG30SUNFUL",
    "KXEPLCORNERS-26AUG30SUNFUL",
    "KXEPLTCORNERS-26AUG30SUNFUL",
    "KXEPLTEAMTOTAL-26AUG30SUNFUL",
)


# =============================================================================
# The fixture key — the only thing that decides "same game"
# =============================================================================


class TestKalshiGameTwinKey:
    def test_every_epl_sibling_yields_one_key(self):
        """RED BEFORE THE FIX: no key existed, so nine tickers were nine games."""
        assert {kalshi_game_twin_key(t) for t in SUNFUL_SIBLINGS} == {
            "soccer_epl:26AUG30SUNFUL"
        }

    def test_the_sport_qualifies_the_token(self):
        """A bare token must never key anything — Alex, 2026-08-21."""
        epl = kalshi_game_twin_key("KXEPLBTTS-26AUG30SUNFUL")
        nfl = kalshi_game_twin_key("KXNFLGAME-26AUG30SUNFUL")
        assert epl != nfl
        assert epl.startswith("soccer_epl:")
        assert nfl.startswith("americanfootball_nfl:")

    def test_season_futures_carry_no_fixture_token(self):
        """The CERT-409 hazard, unreachable rather than re-guarded.

        A date-shaped futures ticker promoted to a game anchor can absorb one of
        its own fixtures. Here the exclusion is free: there is no fixture token
        in a season market to find.
        """
        for ticker in ("KXEPLTOP4-26", "KXEPLGB-26", "KXEPLREL-26"):
            assert kalshi_game_twin_key(ticker) is None

    def test_an_unresolvable_sport_yields_no_key(self):
        assert kalshi_game_twin_key("KXNOTASPORT-26AUG30SUNFUL") is None
        assert kalshi_game_twin_key("") is None
        assert kalshi_game_twin_key(None) is None

    def test_tennis_agrees_with_the_tour_scoped_key_it_generalises(self):
        """Q435's key is this key plus a tour restriction. They must not drift."""
        for ticker in (
            "KXATPMATCH-26AUG30BUBWOL",
            "KXATPSETWINNER-26AUG30BUBWOL-1",
            "KXWTAMATCH-26AUG30SWIRYB",
        ):
            assert kalshi_game_twin_key(ticker) == kalshi_match_segment_key(ticker)


# =============================================================================
# The drain, executed against a recording session
# =============================================================================


class _Row:
    """One (market, event) pair as the drain's single SELECT returns it."""

    def __init__(self, external_id, event_id, commence_time_source):
        self.external_id = external_id
        self.event_id = event_id
        self.commence_time_source = commence_time_source
        self.commence_time = NOW - timedelta(days=1)

    def __iter__(self):
        return iter(
            (
                self.external_id,
                self.event_id,
                self.commence_time_source,
                self.commence_time,
            )
        )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Serves the drain's SELECT and records the tag UPDATEs it issues."""

    def __init__(self, rows):
        self._rows = rows
        self.tags = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        if params is not None:
            # `_tag_duplicate_of`'s Core UPDATE, the one writer of the tag.
            self.tags.append((params["event_id"], params["tag_array"]))
            return _Result([])
        return _Result(self._rows)

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — error path only
        pass


def _tagged(session):
    """{event_id: canonical_event_id} from the recorded writes."""
    out = {}
    for event_id, tag_array in session.tags:
        tag = tag_array.strip('[]"')
        assert tag.startswith(DUPLICATE_TAG_PREFIX), tag
        out[event_id] = int(tag[len(DUPLICATE_TAG_PREFIX):])
    return out


@pytest.mark.asyncio
class TestDrainKalshiTokenTwins:
    async def test_the_specimen_tags_all_three_epl_twins(self):
        """RED BEFORE THE FIX: nothing is tagged and the rail prints eight."""
        session = _FakeSession(
            [
                # The real rows, each already holding a Kalshi market.
                _Row("KXEPLGAME-26AUG30MUNIPS", 15290890, "espn"),
                _Row("KXEPLGAME-26AUG30SUNFUL", 15290898, "espn"),
                _Row("KXEPLGAME-26AUG30CFCBRI", 15290743, "espn"),
                # The auto-created twins.
                _Row("KXEPLTOTAL-26AUG30MUNIPS", 15298940, "kalshi_ticker"),
                _Row("KXEPLBTTS-26AUG30SUNFUL", 15298364, "kalshi_ticker"),
                _Row("KXEPLFTTS-26AUG30SUNFUL", 15299046, "kalshi_ticker"),
                _Row("KXEPLSCORE-26AUG30CFCBRI", 15297751, "kalshi_ticker"),
            ]
        )
        stats = await _drain_kalshi_token_twins(session, NOW)

        assert _tagged(session) == {
            15298940: 15290890,
            15298364: 15290898,
            15299046: 15290898,
            15297751: 15290743,
        }
        assert stats["tagged"] == 4
        assert stats["split_tokens"] == 3
        assert stats["ambiguous"] == 0
        assert stats["refused_schedule_derived"] == 0
        assert session.commits == 1

    async def test_a_lone_fixture_is_never_touched(self):
        """Nine series on ONE event is the healthy shape, not a duplicate."""
        session = _FakeSession(
            [_Row(t, 15290898, "espn") for t in SUNFUL_SIBLINGS]
        )
        stats = await _drain_kalshi_token_twins(session, NOW)

        assert session.tags == []
        assert stats["split_tokens"] == 0
        assert stats["tokens"] == 1
        assert session.commits == 0

    async def test_two_ticker_derived_twins_are_refused(self):
        """No schedule-derived row means no forced choice. Refuse, don't flip."""
        session = _FakeSession(
            [
                _Row("KXEPLBTTS-26AUG30SUNFUL", 991, "kalshi_ticker"),
                _Row("KXEPLFTTS-26AUG30SUNFUL", 992, "kalshi_ticker"),
            ]
        )
        stats = await _drain_kalshi_token_twins(session, NOW)

        assert session.tags == []
        assert stats["ambiguous"] == 1
        assert stats["tagged"] == 0

    async def test_two_schedule_derived_rows_are_refused(self):
        """A doubleheader whose ticker carries no HHMM. Both rows are real."""
        session = _FakeSession(
            [
                _Row("KXMLBGAME-26AUG30COLCIN", 881, "odds_api"),
                _Row("KXMLBGAME-26AUG30COLCIN", 882, "espn"),
            ]
        )
        stats = await _drain_kalshi_token_twins(session, NOW)

        assert session.tags == []
        assert stats["ambiguous"] == 1

    async def test_a_schedule_derived_row_is_never_tagged(self):
        """THE INVARIANT. Executed, not read out of the chooser's docstring.

        The chooser is handed a group in which the survivor is schedule-derived
        and one loser is ALSO schedule-derived — a state `_choose_segment_event`
        will not produce today. The drain must refuse the write rather than
        assume its caller upstream cannot change.
        """
        import app.tasks.prediction_market_matching as pmm

        real_chooser = pmm._choose_segment_event
        pmm._choose_segment_event = lambda ids, prov: (901, "schedule_derived")
        try:
            session = _FakeSession(
                [
                    _Row("KXEPLGAME-26AUG30SUNFUL", 901, "espn"),
                    _Row("KXEPLBTTS-26AUG30SUNFUL", 902, "odds_api"),
                ]
            )
            stats = await _drain_kalshi_token_twins(session, NOW)
        finally:
            pmm._choose_segment_event = real_chooser

        assert session.tags == [], "a schedule-derived row was tagged"
        assert stats["refused_schedule_derived"] == 1
        assert stats["tagged"] == 0

    async def test_season_futures_never_group_with_a_fixture(self):
        session = _FakeSession(
            [
                _Row("KXEPLTOP4-26", 771, "kalshi_ticker"),
                _Row("KXEPLGB-26", 772, "kalshi_ticker"),
            ]
        )
        stats = await _drain_kalshi_token_twins(session, NOW)

        assert session.tags == []
        assert stats["tokens"] == 0

    async def test_the_window_stays_on_the_cheap_side_of_the_planner_cliff(self):
        """The lookback is a COST bound and 7 is where the plan flips.

        Measured on production 2026-08-31, root-node blocks over the exact
        statement this task compiles: 7 days = 53,320 (three reps, +-3), 14 days
        = 277,016. That is a sequential scan of `futures_markets`, not a slope —
        it costs the same at 14 days, 21 days, and a `-16d..+60d` band. At 96
        runs a day it is ~26 GB of buffer traffic against a database at 103% of
        its plan.

        Widening this constant is a real decision with a real price. If you need
        broader coverage, drive the drain off ticker-derived events (33,394
        blocks, no window at all) and read siblings per (sport, day) — do not
        just raise the number.
        """
        from app.tasks.prediction_market_matching import (
            TWIN_DRAIN_LOOKBACK_DAYS,
        )

        assert TWIN_DRAIN_LOOKBACK_DAYS <= 7, (
            "the drain's window crossed the measured planner cliff at 14 days "
            "(53,320 -> 277,016 root blocks, every 15 minutes)"
        )

    async def test_the_window_actually_bounds_the_read(self):
        """The constant must reach the statement, not just sit in the module."""
        captured = {}

        class _Capture(_FakeSession):
            async def execute(self, stmt, params=None):
                if params is None:
                    captured["sql"] = str(
                        stmt.compile(
                            dialect=postgresql.dialect(),
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                return await super().execute(stmt, params)

        session = _Capture([])
        await _drain_kalshi_token_twins(session, NOW)

        from app.tasks.prediction_market_matching import (
            TWIN_DRAIN_LOOKBACK_DAYS,
        )

        cutoff = NOW - timedelta(days=TWIN_DRAIN_LOOKBACK_DAYS)
        assert cutoff.date().isoformat() in captured["sql"], (
            f"the emitted statement does not bound on {cutoff.date()}: "
            f"{captured.get('sql', '<no SELECT issued>')[:400]}"
        )

    async def test_a_broken_session_returns_stats_and_does_not_raise(self):
        """gotcha #42 posture: this must never take the matcher down with it."""

        class _Boom:
            async def execute(self, *a, **k):
                raise RuntimeError("db gone")

            async def rollback(self):
                self.rolled_back = True

        boom = _Boom()
        stats = await _drain_kalshi_token_twins(boom, NOW)
        assert stats["tagged"] == 0
        assert getattr(boom, "rolled_back", False) is True


# =============================================================================
# The consumer — the predicate the rails read the proof with
# =============================================================================


def _sql(stmt):
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestNotAProvenDuplicate:
    def test_the_predicate_binds_the_alias_it_is_given(self):
        """A hand-written fragment naming `events` reads the WRONG table here.

        The RECENT RESULTS rail selects from an ALIAS of `events` (the
        optimization fence's subquery). A predicate hardcoding the table name
        compiles fine and silently filters the outer table instead — so this
        asserts the correlation lands on the alias and that the table name does
        NOT appear inside the EXISTS.
        """
        al = aliased(Event, name="fenced")
        sql = _sql(select(al.id).where(not_a_proven_duplicate(al)))
        exists_clause = sql[sql.index("EXISTS") :]
        assert "fenced.event_tags" in exists_clause
        assert "events.event_tags" not in exists_clause

    def test_the_predicate_spells_the_prefix_from_the_writer(self):
        sql = _sql(select(Event.id).where(not_a_proven_duplicate()))
        assert DUPLICATE_TAG_PREFIX in sql

    def test_it_matches_any_canonical_id_not_one_it_has_to_guess(self):
        """Containment would need the whole tag; the reader cannot know the id."""
        sql = _sql(select(Event.id).where(not_a_proven_duplicate()))
        assert "LIKE" in sql
        assert "@>" not in sql


class TestBothLeagueRailsReadTheProof:
    def test_recent_results_filters_proven_duplicates(self):
        sql = _sql(recent_results_query("soccer_epl", NOW))
        assert DUPLICATE_TAG_PREFIX in sql

    def test_upcoming_games_filters_proven_duplicates(self):
        sql = _sql(upcoming_games_query("soccer_epl", NOW))
        assert DUPLICATE_TAG_PREFIX in sql

    def test_the_optimization_fence_survives(self):
        """LAT-P110 / #2260: removing `OFFSET 0` re-opens a 4.9s cold read.

        The filter was put on the OUTER select precisely so the fenced inner
        statement stays byte-identical to the one every block count in
        `recent_results_query`'s docstring was measured on.
        """
        sql = _sql(recent_results_query("soccer_epl", NOW))
        inner = sql[sql.index("FROM (") : sql.index(") AS anon_1")]
        assert "OFFSET 0" in inner
        assert DUPLICATE_TAG_PREFIX not in inner, (
            "the duplicate filter leaked into the fenced subquery — every plan "
            "number in the docstring now describes a statement we do not run"
        )

    def test_the_cap_is_applied_after_the_filter_so_the_rail_refills(self):
        """Dropping four twins must promote four real games, not shorten the rail.

        Measured on production 2026-08-31 by running this exact statement with
        the prefix swapped for one the twins DO carry (`provenance:source:kalshi`):
        the rail came back with nine real scorelines instead of four real and
        five scoreless. That only works because LIMIT follows the WHERE.
        """
        sql = _sql(recent_results_query("soccer_epl", NOW))
        assert sql.index(DUPLICATE_TAG_PREFIX) < sql.rindex("LIMIT")
