"""#6230 — one team, one record.

A reader on the iPhone event page for Twins v Yankees saw the hero say
``Minnesota Twins 70-79`` and the Championship Path card, one scroll down —
one *screen* down on iPad — say ``Twins 10-18-1``. ``10-18-1`` cannot be an MLB
record; MLB has no ties.

The two numbers come from two different `teams` rows for the same club:

    855   Minnesota Twins  10-18-1  baseball_mlb_preseason   <- spring training
    10739 Minnesota Twins  70-79    baseball_mlb

`_get_team_metadata` matches on ``Team.name ILIKE '%name%'`` with no sport
scope and writes last-one-wins, so which row supplied the record was decided by
the order Postgres returned. That is why 19 of 24 sampled clubs were wrong and
five — Yankees among them — were right: nothing about those clubs differs.

These guards pin the two halves of the repair that can each rot on their own:
the league's ``sport_keys`` is consulted (so the season row wins), and the
chooser is *order-independent* (so a green suite cannot be an accident of the
order the fake happened to hand over). The third guard pins the deliberate
non-regression: an out-of-scope row is still used when it is the only row, so
the fix cannot quietly delete a logo, a colour or a conference from a league
whose teams sit under a sport key its config does not list.
"""

import pytest

from app.routes.playoffs import _get_team_metadata


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(self, team_id, name, sport_key, record, abbreviation=None):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.current_record = record
        self.abbreviation = abbreviation
        self.logo_url_small = None
        self.logo_url_large = None
        self.primary_color = None
        self.secondary_color = None
        self.standings_data = None
        self.alternate_names = []


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Returns every row the ILIKE would have matched, in the given order.

    The order is the point: the real query has no ORDER BY, so the production
    defect is a property of which row arrives last.
    """

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _twins_rows():
    """The measured production pair, 2026-09-14."""
    return [
        _FakeTeam(855, "Minnesota Twins", "baseball_mlb_preseason", "10-18-1", "MIN"),
        _FakeTeam(10739, "Minnesota Twins", "baseball_mlb", "70-79", "MIN"),
    ]


class TestTheSeasonRowWins:
    @pytest.mark.asyncio
    async def test_preseason_record_does_not_reach_the_grid(self):
        """Named for the reader's complaint — and it PASSES on the parent.

        In this order the season row is already last, so last-one-wins gets the
        right answer by luck. Kept because it is the sentence the issue is
        about, but it is not the proof: the next test is.
        """
        rows = _twins_rows()
        meta = await _get_team_metadata(
            _FakeSession(rows), {"Minnesota Twins"}, league_slug="mlb"
        )

        assert meta["minnesota twins"]["record"] == "70-79"
        assert meta["minnesota twins"]["team_id"] == 10739

    @pytest.mark.asyncio
    async def test_the_answer_does_not_depend_on_row_order(self):
        """The whole bug in one assertion.

        Both orders must give the same record. Before the fix the first order
        gave 70-79 and the second gave 10-18-1, which is exactly how the same
        club read correctly on one page and wrongly on another.
        """
        forward = await _get_team_metadata(
            _FakeSession(_twins_rows()), {"Minnesota Twins"}, league_slug="mlb"
        )
        reverse = await _get_team_metadata(
            _FakeSession(list(reversed(_twins_rows()))),
            {"Minnesota Twins"},
            league_slug="mlb",
        )

        assert forward["minnesota twins"]["record"] == reverse["minnesota twins"]["record"]
        assert reverse["minnesota twins"]["record"] == "70-79"

    @pytest.mark.asyncio
    async def test_the_abbreviation_index_agrees_with_the_name_index(self):
        """Both clubs' rows carry MIN, so the alias must not point at the loser."""
        meta = await _get_team_metadata(
            _FakeSession(list(reversed(_twins_rows()))),
            {"Minnesota Twins"},
            league_slug="mlb",
        )

        assert meta["min"]["record"] == "70-79"
        assert meta["min"] is meta["minnesota twins"]


class TestNothingIsLostToTheScope:
    @pytest.mark.asyncio
    async def test_an_out_of_scope_row_is_still_used_when_it_is_the_only_row(self):
        """A preference, not a filter.

        A hard `sport.key IN (...)` would answer this case with nothing, taking
        the logo, colours and conference with it.
        """
        rows = [_FakeTeam(4242, "Hokkaido Nippon-Ham Fighters", "baseball_npb", "72-68")]

        meta = await _get_team_metadata(
            _FakeSession(rows), {"Hokkaido Nippon-Ham Fighters"}, league_slug="mlb"
        )

        assert meta["hokkaido nippon-ham fighters"]["record"] == "72-68"

    @pytest.mark.asyncio
    async def test_no_league_slug_keeps_the_old_deterministic_behaviour(self):
        """With no config there is no scope to prefer — highest id still wins."""
        rows = _twins_rows()

        forward = await _get_team_metadata(_FakeSession(rows), {"Minnesota Twins"})
        reverse = await _get_team_metadata(
            _FakeSession(list(reversed(rows))), {"Minnesota Twins"}
        )

        assert forward["minnesota twins"]["record"] == "70-79"
        assert reverse["minnesota twins"]["record"] == "70-79"

    @pytest.mark.asyncio
    async def test_two_in_scope_rows_break_the_tie_on_id_not_on_order(self):
        rows = [
            _FakeTeam(100, "Seattle Mariners", "baseball_mlb", "stale"),
            _FakeTeam(200, "Seattle Mariners", "baseball_mlb", "fresh"),
        ]

        forward = await _get_team_metadata(
            _FakeSession(rows), {"Seattle Mariners"}, league_slug="mlb"
        )
        reverse = await _get_team_metadata(
            _FakeSession(list(reversed(rows))), {"Seattle Mariners"}, league_slug="mlb"
        )

        assert forward["seattle mariners"]["record"] == "fresh"
        assert reverse["seattle mariners"]["record"] == "fresh"

    @pytest.mark.asyncio
    async def test_a_single_in_scope_row_is_untouched(self):
        """Control: the overwhelming majority of clubs have one row."""
        rows = [_FakeTeam(6610, "New York Yankees", "baseball_mlb", "86-63", "NYY")]

        meta = await _get_team_metadata(
            _FakeSession(rows), {"New York Yankees"}, league_slug="mlb"
        )

        assert meta["new york yankees"]["record"] == "86-63"
        assert meta["new york yankees"]["team_id"] == 6610
        assert meta["nyy"] is meta["new york yankees"]

    @pytest.mark.asyncio
    async def test_a_row_whose_sport_did_not_load_ranks_out_of_scope_and_does_not_raise(self):
        """The grid degrading to today's behaviour is survivable; a 500 is not."""

        class _NoSport(_FakeTeam):
            def __init__(self):
                super().__init__(77, "Detroit Tigers", "baseball_mlb", "70-79", "DET")
                self.sport = None

        meta = await _get_team_metadata(
            _FakeSession([_NoSport()]), {"Detroit Tigers"}, league_slug="mlb"
        )

        assert meta["detroit tigers"]["record"] == "70-79"


class TestTheScopeKeyIsTheLeaguesOwn:
    def test_mlb_config_does_not_list_the_preseason_sport_key(self):
        """If this ever changes, the fix above silently stops working.

        The whole repair rests on `baseball_mlb_preseason` being absent from the
        league's own `sport_keys`; a future edit that adds it would re-admit the
        spring-training row with no test failing anywhere else.
        """
        from app.config.league_configs import get_league_config

        keys = get_league_config("mlb").sport_keys
        assert "baseball_mlb" in keys
        assert "baseball_mlb_preseason" not in keys
