"""#1980 — the ``espn_id`` manufacturer: a two-day pool selected on names alone.

Queue 380/381 repaired 17 rows carrying a wrong ``espn_id``. The repair rail
works, but it does not stop the manufacturing, and the signature of the damage
was specific enough to name the writer: **±15 / ±30 offsets against a CORRECT
``commence_time`` on 15 of 17 rows.**

``app/utils/espn_candidate_selection.py`` carries the full derivation. The short
version, and what these tests pin:

* ``discover_events`` widens the ESPN candidate pool to TWO calendar days to
  survive ESPN's US-Eastern date boundaries. That widening is correct.
* It then selected from that pool on **team names only**, taking the first hit.
* MLB teams play 3–4 game series on consecutive days, so both days' games match
  the names. The first hit is the ``date_str`` bucket, which for a late/West
  Coast game is the FOLLOWING day's slate.
* ESPN ids run in schedule order and an MLB slate is ~15 games, so "one day off
  in the same series" is an id off by ~15, and two days off by ~30.

The regression these tests guard is therefore not "names_match is loose" (that
is #2046, and it compounds this one) but "a two-day pool was never narrowed
back down by time".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.espn_candidate_selection import select_espn_candidate


# ── fixtures ────────────────────────────────────────────────────────────────


class _Team:
    """Minimal stand-in for ``ESPNTeam`` (only the fields the selector reads)."""

    def __init__(self, display_name, name=None):
        self.display_name = display_name
        self.name = name or display_name


class _Game:
    """Minimal stand-in for ``ESPNEvent``."""

    def __init__(self, espn_id, home, away, date):
        self.espn_id = str(espn_id)
        self.home_team = _Team(home) if home else None
        self.away_team = _Team(away) if away else None
        self.date = date


UTC = timezone.utc


def _series(home, away, first_pitch, *, base_id, games=3, slate=15):
    """A real MLB series: same two clubs, consecutive days, ids a slate apart."""
    return [
        _Game(base_id + (n * slate), home, away, first_pitch + timedelta(days=n))
        for n in range(games)
    ]


# ── the defect ──────────────────────────────────────────────────────────────


class TestSeriesSiblingIsNotStamped:
    """The headline: a two-day pool must not hand back the wrong day's game."""

    def test_late_game_does_not_take_the_next_days_id(self):
        """The production shape: a 10pm ET game whose UTC date is tomorrow.

        ``date_str`` resolves to the FOLLOWING day's ET slate, so under the old
        first-match-wins loop the pool presented game 2 of the series first and
        that is the id that got stamped. Offset: +15 — the observed signature.
        """
        # Aug 18, 10:05pm ET  ==  Aug 19, 02:05 UTC
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        game1, game2, game3 = _series(
            "Los Angeles Dodgers", "San Francisco Giants",
            commence, base_id=401816140,
        )
        # The pool as sports.py builds it: date_str bucket FIRST, then prev_date.
        # date_str == 20260819 holds game 2; prev_date == 20260818 holds game 1.
        pool = [game2, game1]

        _date, espn_id = select_espn_candidate(
            pool, "Los Angeles Dodgers", "San Francisco Giants", commence,
        )

        assert espn_id == game1.espn_id, (
            "stamped the NEXT game of the series — this is the +15 offset "
            f"#1980 measured (got {espn_id}, wanted {game1.espn_id})"
        )

    def test_returned_date_matches_the_returned_game(self):
        """The id and the time must come from the SAME game.

        They are read together into ``espn_event_id`` / ``espn_commence_time``,
        and the second one feeds the commence-time correction.
        """
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        game1, game2, _ = _series(
            "New York Yankees", "Boston Red Sox", commence, base_id=401816200,
        )

        date, espn_id = select_espn_candidate(
            [game2, game1], "New York Yankees", "Boston Red Sox", commence,
        )

        assert (date, espn_id) == (game1.date, game1.espn_id)

    def test_previous_days_game_is_not_taken_either(self):
        """The other sign: ``-15``. The pool order must not decide it."""
        commence = datetime(2026, 8, 19, 23, 10, tzinfo=UTC)
        yesterday = _Game(
            401816300, "Chicago Cubs", "St. Louis Cardinals",
            commence - timedelta(days=1),
        )
        today = _Game(401816315, "Chicago Cubs", "St. Louis Cardinals", commence)

        _date, espn_id = select_espn_candidate(
            [yesterday, today], "Chicago Cubs", "St. Louis Cardinals", commence,
        )

        assert espn_id == today.espn_id

    @pytest.mark.parametrize("offset_days", [1, 2])
    def test_offset_is_not_reachable_at_one_or_two_days(self, offset_days):
        """±15 and ±30 are the two measured offsets; pin both."""
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        right = _Game(401816400, "Houston Astros", "Seattle Mariners", commence)
        wrong = _Game(
            401816400 + (15 * offset_days), "Houston Astros", "Seattle Mariners",
            commence + timedelta(days=offset_days),
        )

        _date, espn_id = select_espn_candidate(
            [wrong, right], "Houston Astros", "Seattle Mariners", commence,
        )

        assert espn_id == right.espn_id


# ── the narrowness of the change ────────────────────────────────────────────


class TestSingleMatchIsUnchanged:
    """The two-day pool was widened to fix a real bug. Do not un-fix it."""

    def test_et_boundary_game_still_resolves_from_the_previous_day_bucket(self):
        """The case the widening exists for: only ONE candidate, a day 'off'.

        A 10pm ET game sits in ESPN's previous-UTC-date bucket. With a single
        name match the selector must still return it, however far away it looks
        — that is the original bug the two-day pool fixed.
        """
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        only = _Game(
            401816500, "Los Angeles Angels", "Texas Rangers",
            commence - timedelta(hours=4),
        )

        date, espn_id = select_espn_candidate(
            [only], "Los Angeles Angels", "Texas Rangers", commence,
        )

        assert (date, espn_id) == (only.date, only.espn_id)

    def test_no_name_match_returns_nothing(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        pool = [_Game(401816600, "Miami Marlins", "Atlanta Braves", commence)]

        assert select_espn_candidate(
            pool, "Detroit Tigers", "Minnesota Twins", commence,
        ) == (None, None)

    def test_teamless_candidates_are_skipped_not_crashed_on(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        broken = _Game(401816700, None, None, commence)
        real = _Game(401816701, "Toronto Blue Jays", "Baltimore Orioles", commence)

        _date, espn_id = select_espn_candidate(
            [broken, real], "Toronto Blue Jays", "Baltimore Orioles", commence,
        )

        assert espn_id == real.espn_id

    def test_empty_pool(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        assert select_espn_candidate([], "A", "B", commence) == (None, None)


class TestDeterminism:
    """Doubleheaders are a real same-day same-teams pair — stay deterministic."""

    def test_exact_tie_keeps_the_earlier_candidate(self):
        commence = datetime(2026, 8, 19, 17, 0, tzinfo=UTC)
        first = _Game(401816800, "Cleveland Guardians", "Kansas City Royals", commence)
        second = _Game(401816801, "Cleveland Guardians", "Kansas City Royals", commence)

        _d1, id1 = select_espn_candidate(
            [first, second], "Cleveland Guardians", "Kansas City Royals", commence,
        )
        _d2, id2 = select_espn_candidate(
            [first, second], "Cleveland Guardians", "Kansas City Royals", commence,
        )

        assert id1 == id2 == first.espn_id

    def test_dateless_candidate_never_wins_over_a_dated_one(self):
        commence = datetime(2026, 8, 19, 2, 5, tzinfo=UTC)
        dateless = _Game(401816900, "New York Mets", "Philadelphia Phillies", None)
        dated = _Game(401816901, "New York Mets", "Philadelphia Phillies", commence)

        _date, espn_id = select_espn_candidate(
            [dateless, dated], "New York Mets", "Philadelphia Phillies", commence,
        )

        assert espn_id == dated.espn_id


# ── the call site ───────────────────────────────────────────────────────────


class TestCallSiteRoutesThroughTheSelector:
    """A guard that the inlined loop does not grow back (cf. #2017's test)."""

    def test_sports_py_imports_and_uses_the_selector(self):
        import inspect

        from app.tasks import sports

        src = inspect.getsource(sports)
        assert "select_espn_candidate" in src, (
            "discover_events must select its ESPN candidate through the shared "
            "selector — an inlined names-only loop is the #1980 manufacturer"
        )
