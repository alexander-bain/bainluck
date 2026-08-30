"""#2352 — the spread grader stops handing every away leg the home team's margin.

`_spread_outcome_is_winner` used to pick its side with a bare token intersection,
home first::

    if team_tokens & home_tokens:      margin = home - away
    elif team_tokens & away_tokens:    margin = away - home

Where the two clubs share a city, the city tokens alone satisfy the first branch,
so the AWAY ladder was graded off the HOME margin. Measured over all 17,064
production `game_score` spread rows on 2026-08-30: 39 rows wrong, 27 of them
directly attributable to the collision. The class is catalogued in this repo as
``SHARED_CITY_DIFFERENT_CLUB`` (``test_names_match_authority_2046.py``).

The fix reuses ``_exclusive_team_side``, the helper #2351 added for the
team-total grader, so this module now has ONE side-picker instead of three.

Guard discipline (LAT-P154's lesson, re-earned): nothing here asserts via
``inspect.getsource``. This module's docstrings quote their own SQL and their own
predicates, so a source-text guard goes vacuous the moment the statement and the
prose disagree. Every guard below drives the real function or records the
statement the code actually EXECUTES.
"""

import re

import pytest

from app.tasks.backfill_winners import (
    _PERIOD_SPREAD_NAME_RE,
    _SPREAD_RE,
    _spread_outcome_is_winner,
)


# --------------------------------------------------------------------------
# Production rows, copied from the measured census. Each carries the real final
# score, so a guard that drifts from reality fails rather than agreeing with me.
# --------------------------------------------------------------------------

#: (outcome name, home, away, home_score, away_score, expected)
SHARED_CITY_AWAY_LEGS = [
    # The row the census flagged first: the Devils won 6-3 on the road and the
    # old code read the Rangers' -3.
    ("New Jersey wins by over 1.5 goals",
     "New York Rangers", "New Jersey Devils", 3, 6, True),
    ("New Jersey wins by over 2.5 goals",
     "New York Rangers", "New Jersey Devils", 3, 6, True),
    # Same fixture with the sides swapped — the Rangers lost by 3 away.
    ("New York R wins by over 1.5 goals",
     "New Jersey Devils", "New York Rangers", 6, 3, False),
    # NBA, and the discriminator is a SINGLE LETTER (Kalshi abbreviates the club,
    # not the city). Clippers lost by 3 away; the old code read the Lakers' +3.
    ("Los Angeles C wins by over 2.5 Points",
     "Los Angeles Lakers", "Los Angeles Clippers", 125, 122, False),
    # NCAAMB — "UC" is a shared token across the whole University of California
    # system, which is why NCAAMB carried 17 of the 39 wrong rows.
    ("UC Davis wins by over 3.5 Points",
     "UC Irvine Anteaters", "UC Davis Aggies", 79, 69, False),
    ("UC Santa Barbara wins by over 2.5 Points",
     "UC Davis Aggies", "UC Santa Barbara Gauchos", 79, 73, False),
    ("UC Riverside wins by over 1.5 Points",
     "UC Santa Barbara Gauchos", "UC Riverside Highlanders", 70, 59, False),
    # "Utah" and "Virginia" are shared-word collisions rather than shared cities.
    ("Utah Tech wins by over 1.5 Points",
     "Southern Utah Thunderbirds", "Utah Tech Trailblazers", 81, 67, False),
    ("Utah Valley wins by over 3.5 Points",
     "Southern Utah Thunderbirds", "Utah Valley Wolverines", 88, 92, True),
    ("Virginia Tech wins by over 3.5 Points",
     "Virginia Cavaliers", "Virginia Tech Hokies", 76, 72, False),
    # MLB: "San Diego" vs "San Francisco" share nothing — but the OLD code still
    # got this one wrong for a different reason, so it is kept as a control that
    # the fix repairs it too.
    ("San Diego wins by over 1.5 runs",
     "San Francisco Giants", "San Diego Padres", 1, 5, True),
]

#: Claims that name nothing but shared tokens. Refusing is the DESIGNED outcome —
#: `game_score` is Tier-1 and gotcha #21 says an ungraded row beats a wrong one.
AMBIGUOUS_CLAIMS = [
    # "Virginia" is a subset of BOTH "Virginia Cavaliers" and "Virginia Tech
    # Hokies", so no discriminator survives.
    ("Virginia wins by over 12.5 Points",
     "Virginia Cavaliers", "Virginia Tech Hokies", 76, 72),
    # No remaining token starts with "ws".
    ("Chicago WS wins by over 1.5 runs",
     "Chicago Cubs", "Chicago White Sox", 4, 3),
    ("Chicago WS wins by over 3.5 runs",
     "Chicago White Sox", "Chicago Cubs", 9, 8),
    # Serie A: strip the shared "milan" and nothing is left.
    ("Milan wins by over 1.5 goals", "AC Milan", "Inter Milan", 1, 0),
]


class TestSharedCityAwayLegs:
    """The defect itself: an away leg must be graded off the AWAY margin."""

    @pytest.mark.parametrize(
        "name,home,away,hs,as_,expected", SHARED_CITY_AWAY_LEGS
    )
    def test_leg_grades_against_its_own_team(self, name, home, away, hs, as_, expected):
        assert _spread_outcome_is_winner(name, home, away, hs, as_) is expected

    def test_the_old_home_first_rule_would_have_failed_these(self):
        """Pin that these rows actually EXERCISE the defect.

        A guard that passes both before and after the fix proves nothing. This
        reproduces the pre-#2352 side-picker verbatim and asserts it disagrees
        with the shipped grader on every shared-city row — so if someone
        reverts the fix, the parametrized guards above go red for a real reason.
        """
        from app.utils.name_normalization import normalize_team_name

        def old(name, home, away, hs, as_):
            sm = _SPREAD_RE.search(name)
            line = float(sm.group(2))
            ht = set(normalize_team_name(home).split())
            at = set(normalize_team_name(away).split())
            tt = set(normalize_team_name(sm.group(1).strip()).split())
            if tt & ht:
                margin = hs - as_
            elif tt & at:
                margin = as_ - hs
            else:
                return None
            return margin > line

        disagreements = [
            name
            for name, home, away, hs, as_, expected in SHARED_CITY_AWAY_LEGS
            if old(name, home, away, hs, as_) is not expected
        ]
        # Every row but the two "San Diego"/"Utah Valley"-style controls, whose
        # clubs share no token, is a genuine collision.
        assert len(disagreements) >= 9, disagreements

    def test_the_home_leg_of_the_same_matchup_is_still_right(self):
        # Lakers won by 3 at home; their own ladder must still clear 2.5.
        assert _spread_outcome_is_winner(
            "Los Angeles L wins by over 2.5 Points",
            "Los Angeles Lakers", "Los Angeles Clippers", 125, 122,
        ) is True


class TestAmbiguousClaimsAreRefused:
    @pytest.mark.parametrize("name,home,away,hs,as_", AMBIGUOUS_CLAIMS)
    def test_refuses_rather_than_guessing(self, name, home, away, hs, as_):
        assert _spread_outcome_is_winner(name, home, away, hs, as_) is None

    def test_the_longer_sibling_in_the_same_market_still_resolves(self):
        """`Virginia` refuses but `Virginia Tech` must not.

        Both legs live in the same market. Refusing the ambiguous one is only
        acceptable because the discriminating one still grades.
        """
        args = ("Virginia Cavaliers", "Virginia Tech Hokies", 76, 72)
        assert _spread_outcome_is_winner("Virginia wins by over 3.5 Points", *args) is None
        assert _spread_outcome_is_winner(
            "Virginia Tech wins by over 3.5 Points", *args
        ) is False


class TestDistinctCitiesAreUnaffected:
    """The fix must not cost recall where the clubs share nothing."""

    @pytest.mark.parametrize(
        "name,home,away,hs,as_,expected",
        [
            ("Denver wins by over 6.5 Points",
             "Denver Nuggets", "Houston Rockets", 129, 93, True),
            ("Houston wins by over 6.5 Points",
             "Denver Nuggets", "Houston Rockets", 129, 93, False),
            ("Arkansas wins by over 4.5 Points",
             "Arkansas Razorbacks", "High Point Panthers", 94, 88, True),
            # #939's accent case must keep working through the new side-picker.
            ("Montreal wins by over 1.5 goals",
             "Montréal Canadiens", "Boston Bruins", 4, 1, True),
        ],
    )
    def test_unchanged(self, name, home, away, hs, as_, expected):
        assert _spread_outcome_is_winner(name, home, away, hs, as_) is expected

    def test_a_name_that_is_not_a_spread_outcome_is_still_none(self):
        assert _spread_outcome_is_winner(
            "Over 5.5 runs scored", "A", "B", 3, 2
        ) is None

    def test_missing_score_is_still_none(self):
        assert _spread_outcome_is_winner(
            "Denver wins by over 1.5 Points", "Denver Nuggets", "Houston Rockets",
            None, 4,
        ) is None


# --------------------------------------------------------------------------
# The halftime hazard the widened re-grade rail creates.
# --------------------------------------------------------------------------

#: Every distinct period shape in production (measured 2026-08-30, 13 of them).
PRODUCTION_PERIOD_NAMES = [
    "Detroit wins the 1H by over 9.5 points",
    "Detroit wins the 2H by over 10.5 points",
    "Spurs wins 2Q by over 3.5 points",
    "Spurs wins 3Q by over 6.5 points",
    "Louisville wins the 1H by over 17.5 points",
    "Carolina wins 1H by over 9.5 points",
    "Tampa Bay wins 1Q by over 6.5 points",
    "GB Packers wins 2H by over 9.5 points",
    "Tennessee wins 2Q by over 6.5 points",
    "Tampa Bay wins 3Q by over 3.5 points",
    "Arizona wins 4Q by over 6.5 points",
    "Los Angeles wins 1Q by over 1.5 points",
    "Minnesota wins 3Q by over 1.5 points",
]

FULL_GAME_NAMES = [
    "San Diego wins by over 1.5 runs",
    "UC Davis wins by over 3.5 Points",
    "New Jersey wins by over 2.5 goals",
]


class TestPeriodNamesAreRecognised:
    @pytest.mark.parametrize("name", PRODUCTION_PERIOD_NAMES)
    def test_every_production_period_shape_is_flagged(self, name):
        assert _PERIOD_SPREAD_NAME_RE.search(name) is not None

    @pytest.mark.parametrize("name", FULL_GAME_NAMES)
    def test_no_full_game_name_is_flagged(self, name):
        assert _PERIOD_SPREAD_NAME_RE.search(name) is None

    def test_spread_re_still_matches_the_1h_shape(self):
        """Do not "fix" `_SPREAD_RE` to exclude 1H.

        The MAIN resolver detects `1h` in the ticker and grades those against a
        reconstructed halftime score, so `_SPREAD_RE` must keep matching them.
        Only consumers holding the full-time score exclude them. This guard
        exists so the two rules cannot be collapsed by a later reader.
        """
        m = _SPREAD_RE.search("Detroit wins the 1H by over 9.5 points")
        assert m is not None and m.group(1) == "Detroit"


# --------------------------------------------------------------------------
# The re-grade rail — the only thing that can repair a wrong `game_score` row.
# --------------------------------------------------------------------------


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _RailRecorder:
    """Answers the rail's SELECT and records the statement plus every UPDATE."""

    def __init__(self, rows):
        self._rows = rows
        self.select_sql = None
        self.writes = {}

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if params and "oid" in params:
            self.writes[params["oid"]] = params["won"]
            return _Result([])
        self.select_sql = sql
        return _Result(self._rows)

    async def commit(self):
        return None


class _CM:
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


async def _run_rail(rows, monkeypatch):
    import app.tasks.backfill_winners as bw

    rec = _RailRecorder(rows)
    monkeypatch.setattr(bw, "get_task_session", lambda: _CM(rec))
    stats = await bw._regrade_kalshi_nhl_spread_inversions()
    return rec, stats


def _rail_row(oid, name, home, away, hs, as_, cur):
    return _Row(oid=oid, oc_name=name, home=home, away=away, hs=hs, as_=as_, cur=cur)


@pytest.mark.asyncio
class TestRegradeRail:
    async def test_it_repairs_a_shared_city_away_leg(self, monkeypatch):
        rows = [
            _rail_row(1, "New Jersey wins by over 1.5 goals",
                      "New York Rangers", "New Jersey Devils", 3, 6, False),
        ]
        rec, stats = await _run_rail(rows, monkeypatch)
        assert rec.writes == {1: True}
        assert stats["flipped"] == 1

    async def test_it_writes_nothing_when_the_row_is_already_right(self, monkeypatch):
        rows = [
            _rail_row(1, "New Jersey wins by over 1.5 goals",
                      "New York Rangers", "New Jersey Devils", 3, 6, True),
        ]
        rec, stats = await _run_rail(rows, monkeypatch)
        assert rec.writes == {}
        assert stats["flipped"] == 0

    async def test_a_halftime_row_is_never_graded_off_the_full_time_score(
        self, monkeypatch
    ):
        """The hazard the widening creates, and the second filter that closes it.

        `_SPREAD_RE` matches "wins the 1H by over" on purpose. The rail holds
        only the FULL-TIME score, so if such a row ever reaches the grader it
        writes a wrong `game_score` winner — and `game_score` is not in
        OVERWRITABLE_WINNER_SOURCES_SQL, so that write is permanent.
        """
        rows = [
            _rail_row(1, "Detroit wins the 1H by over 9.5 points",
                      "Detroit Pistons", "Boston Celtics", 120, 100, False),
        ]
        rec, stats = await _run_rail(rows, monkeypatch)
        assert rec.writes == {}, "a halftime leg was graded off the full-time score"
        assert stats["skipped_period"] == 1

    async def test_the_select_excludes_period_tickers(self, monkeypatch):
        """Assert against the statement the rail EXECUTES, not its source text.

        The ticker predicate is the FIRST of the two halftime filters and the
        one that keeps 3,098 production rows out of the result set entirely.
        """
        rec, _ = await _run_rail([], monkeypatch)
        sql = rec.select_sql
        assert sql is not None
        # The widened scope...
        assert re.search(r"external_id\s*~\s*'SPREAD'", sql), sql
        # ...and the exclusion that makes it safe.
        assert re.search(r"external_id\s*!~\s*'\[0-9\]\(H\|Q\|HALF\)SPREAD'", sql), sql

    async def test_the_select_ticker_predicate_actually_excludes_the_period_families(
        self, monkeypatch
    ):
        """Run the SQL regex the statement carries against real tickers.

        A predicate can be present and still be wrong. This extracts the pattern
        from the executed statement and applies it to the production ticker
        families, so the guard fails if the character class ever stops matching
        `KXNBA1HSPREAD` — or starts matching `KXLIGUE1SPREAD`, which contains a
        digit before SPREAD but is a full-game market.
        """
        rec, _ = await _run_rail([], monkeypatch)
        m = re.search(r"external_id\s*!~\s*'([^']+)'", rec.select_sql)
        assert m, rec.select_sql
        exclude = re.compile(m.group(1))

        must_exclude = [
            "KXNBA1HSPREAD-26FEB01DETBOS", "KXNCAAMB1HSPREAD-26JAN02",
            "KXNBA2HSPREAD-26FEB01", "KXNFL1QSPREAD-26SEP07",
            "KXNFL2QSPREAD-26SEP07", "KXNFL3QSPREAD-26SEP07",
            "KXNFL4QSPREAD-26SEP07", "KXWNBA1QSPREAD-26JUN01",
        ]
        must_keep = [
            "KXNCAAMBSPREAD-26JAN02", "KXNBASPREAD-26FEB01",
            "KXMLBSPREAD-26JUN05", "KXNHLSPREAD-26MAR01",
            "KXMLSSPREAD-26MAY01", "KXLIGUE1SPREAD-26MAR01",
        ]
        assert [t for t in must_exclude if not exclude.search(t)] == []
        assert [t for t in must_keep if exclude.search(t)] == []

    async def test_a_refused_leg_is_counted_not_silently_dropped(self, monkeypatch):
        """CERT-499's lesson, applied here before a cert has to find it.

        A row this rail refuses keeps whatever it already holds, forever. The
        refusal IS the final state, so it has to be visible in the verdict.
        """
        rows = [
            _rail_row(1, "Chicago WS wins by over 1.5 runs",
                      "Chicago Cubs", "Chicago White Sox", 4, 3, False),
        ]
        rec, stats = await _run_rail(rows, monkeypatch)
        assert rec.writes == {}
        assert stats["unresolved"] == 1
        assert stats["skipped_period"] == 0

    async def test_checked_counts_every_row_the_select_returned(self, monkeypatch):
        rows = [
            _rail_row(1, "New Jersey wins by over 1.5 goals",
                      "New York Rangers", "New Jersey Devils", 3, 6, False),
            _rail_row(2, "Chicago WS wins by over 1.5 runs",
                      "Chicago Cubs", "Chicago White Sox", 4, 3, False),
            _rail_row(3, "Detroit wins the 1H by over 9.5 points",
                      "Detroit Pistons", "Boston Celtics", 120, 100, False),
        ]
        _, stats = await _run_rail(rows, monkeypatch)
        assert stats["checked"] == 3
        assert stats["flipped"] == 1
        assert stats["unresolved"] == 1
        assert stats["skipped_period"] == 1


# --------------------------------------------------------------------------
# The main resolver's refusal counter.
# --------------------------------------------------------------------------


class _MainRecorder:
    def __init__(self, legs):
        self._legs = legs
        self.writes = {}

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if params and "oid" in params:
            self.writes[params["oid"]] = params["won"]
            return _Result([])
        if "FROM futures_outcomes" in sql:
            return _Result(
                [_Row(market_id=7, id=oid, name=name) for oid, name in self._legs]
            )
        return _Result([])

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.asyncio
class TestMainResolverCountsSpreadRefusals:
    async def _run(self, legs, monkeypatch):
        import app.tasks.backfill_winners as bw

        rec = _MainRecorder(legs)
        monkeypatch.setattr(bw, "get_task_session", lambda: _CM(rec))
        candidate = _Row(
            market_id=7,
            ticker="KXMLBSPREAD-26JUN05CHCCHW",
            market_name="Cubs vs White Sox spread",
            event_id=42,
            home_team_name="Chicago Cubs",
            away_team_name="Chicago White Sox",
            home_score=4,
            away_score=3,
        )
        stats = await bw._resolve_kalshi_spread_total_from_scores(
            {"candidates": [candidate], "locked_market_ids": frozenset()}
        )
        return rec, stats

    async def test_an_unattributable_spread_leg_is_counted(self, monkeypatch):
        rec, stats = await self._run(
            [(1, "Chicago WS wins by over 1.5 runs")], monkeypatch
        )
        assert rec.writes == {}
        assert stats["spread_unresolved_team"] == 1

    async def test_a_resolvable_leg_does_not_increment_the_counter(self, monkeypatch):
        rec, stats = await self._run(
            [(1, "Chicago Cubs wins by over 0.5 runs")], monkeypatch
        )
        assert rec.writes == {1: True}
        assert stats["spread_unresolved_team"] == 0


# --------------------------------------------------------------------------
# The THIRD copy of the side-picker — the one #2352's issue text did not name.
#
# `_resolve_kalshi_period_props` carried its own inline `team_tokens &
# home_tokens` with home-first precedence AND matched on raw `.lower().split()`
# instead of `normalize_team_name`, so it had the shared-city collision *and*
# the #939 accent bug. Production damage is zero — no `scoring_plays` row has
# ever been written for a spread outcome (measured 2026-08-30 across the whole
# `futures_outcomes` spread cohort: the source does not appear at all) — so
# these guards protect a path that is live but has never fired.
# --------------------------------------------------------------------------


class _PeriodResult(_Result):
    def first(self):
        return self._rows[0] if self._rows else None


class _PeriodPropsRecorder:
    """Serves the three SELECTs `_resolve_kalshi_period_props` issues, in order."""

    def __init__(self, market, period_score, outcome):
        self._market = market
        self._period_score = period_score
        self._outcome = outcome
        self.writes = {}

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if params and "oid" in params:
            self.writes[params["oid"]] = params["won"]
            return _PeriodResult([])
        # Order matters: the candidate SELECT joins futures_markets AND carries
        # an `EXISTS (SELECT 1 FROM scoring_plays ...)` subquery, so a
        # scoring_plays test has to come AFTER the futures_markets test or the
        # candidate query is answered with a period-score row.
        if "FROM futures_markets" in sql:
            return _PeriodResult([self._market])
        if "FROM futures_outcomes WHERE market_id" in sql:
            return _PeriodResult([self._outcome])
        if "FROM scoring_plays" in sql:
            return _PeriodResult([self._period_score])
        return _PeriodResult([])

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def _run_period_props(outcome_name, home, away, period_home, period_away,
                            monkeypatch):
    import app.tasks.backfill_winners as bw

    market = _Row(
        market_id=11,
        # "1q" in the ticker selects the quarter branch, which reads the
        # scoring_plays row directly (no halftime subtraction).
        ticker="KXNBA1QSPREAD-26FEB01LALLAC",
        market_name="Lakers vs Clippers 1Q spread",
        event_id=99,
        home_team_name=home,
        away_team_name=away,
        final_home=125,
        final_away=122,
    )
    rec = _PeriodPropsRecorder(
        market,
        _Row(home_score=period_home, away_score=period_away),
        _Row(id=501, name=outcome_name),
    )
    monkeypatch.setattr(bw, "get_task_session", lambda: _CM(rec))
    stats = await bw._resolve_kalshi_period_props()
    return rec, stats


@pytest.mark.asyncio
class TestPeriodPropsSpreadSide:
    async def test_the_away_leg_is_graded_off_the_away_period_margin(
        self, monkeypatch
    ):
        # Clippers (away) won the quarter 30-20; their own +10 must clear 4.5.
        rec, stats = await _run_period_props(
            "Los Angeles C wins by over 4.5 points",
            "Los Angeles Lakers", "Los Angeles Clippers", 20, 30, monkeypatch,
        )
        assert rec.writes == {501: True}, (
            "the away leg was graded off the home team's period margin"
        )
        assert stats["resolved"] == 1

    async def test_the_home_leg_of_the_same_matchup_still_grades(self, monkeypatch):
        rec, _ = await _run_period_props(
            "Los Angeles L wins by over 4.5 points",
            "Los Angeles Lakers", "Los Angeles Clippers", 20, 30, monkeypatch,
        )
        assert rec.writes == {501: False}

    async def test_an_ambiguous_claim_is_refused_not_guessed(self, monkeypatch):
        rec, stats = await _run_period_props(
            "Los Angeles wins by over 4.5 points",
            "Los Angeles Lakers", "Los Angeles Clippers", 20, 30, monkeypatch,
        )
        assert rec.writes == {}
        assert stats["no_parse"] == 1

    async def test_an_accented_event_name_now_matches(self, monkeypatch):
        """#939's bug, which this copy still had: raw `.lower()` never matched.

        Before the conversion the side-picker compared "montreal" against
        "montréal" and fell through to `no_parse`.
        """
        rec, _ = await _run_period_props(
            "Montreal wins by over 0.5 points",
            "Montréal Canadiens", "Boston Bruins", 2, 0, monkeypatch,
        )
        assert rec.writes == {501: True}


class TestTheVerdictSurfacesTheCounters:
    """A counter the task verdict drops is as invisible as no counter at all.

    `_resolve_winners_only` copies a hand-picked subset of each sub-task's stats
    into its summary. `unresolved` and `skipped_period` have to be in that
    subset or nothing operational can ever see them — `skipped_period` climbing
    above zero is the tell that the ticker predicate has stopped excluding a
    Kalshi period family, and that is exactly the signal this fix depends on.

    This reads the source of the REPORTING block rather than driving the whole
    2,000-line task. That is a deliberate exception to this file's no-getsource
    rule, and it is safe for the reason the rule exists: the thing asserted is a
    dict-key copy, not a behaviour, and no docstring in this module quotes these
    two key names in that shape.
    """

    def test_both_new_counters_reach_the_summary(self):
        import inspect

        from app.tasks.backfill_winners import _resolve_winners_only

        src = inspect.getsource(_resolve_winners_only)
        block = src[src.index('stats["nhl_spread_regrade"]'):]
        block = block[: block.index("}")]
        for key in ("checked", "flipped", "unresolved", "skipped_period"):
            assert f'"{key}"' in block, f"{key} is not surfaced in the task verdict"
