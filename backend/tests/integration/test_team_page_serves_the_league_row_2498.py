"""#2498 — a club's page is its league's row, not its spring row.

Alex filed this on his Orioles page on 2026-08-31: the breadcrumb read "MLB
PRESEASON" in August and the record carried a phantom third slot. Measured on
production 2026-09-11, both symptoms are one fact — `GET /api/teams/boston-red-sox`
resolved to team **853**, the `baseball_mlb_preseason` row (`current_record`
13-15, `standings_data` NULL), while the club playing a pennant race sat one slug
away at `boston-red-sox-mlb`, team **10709** (80-67, division East). All 30 MLB
preseason clubs held the clean slug that way; NFL and NBA did not, because their
variant rows carry no `espn_id`.

Every test here drives BOTH directions. A suite that only asserted "the parent is
served" would pass against a change that served the parent unconditionally — and
that is the worse bug, because it would silently pick one of the two St. Louis
Cardinals rows and make a serving route into a second matcher.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.utils.season_variant_team import (
    choose_parent_league_row,
    wants_parent_league_row,
)

# The measured production shape (2026-09-11 22:2xZ), used as the fixture
# throughout so a reader can check the test against the row.
RED_SOX_VARIANT = 853
RED_SOX_PARENT = 10709
CARDINALS_PARENT_A = 10740  # "St. Louis Cardinals", standings_data NULL
CARDINALS_PARENT_B = 13437  # "St.Louis Cardinals" (no space), standings present


# ===========================================================================
# wants_parent_league_row — the cheap gate every team page runs
# ===========================================================================


class TestWantsParentLeagueRow:
    @pytest.mark.parametrize(
        "key",
        ["baseball_mlb_preseason", "americanfootball_nfl_preseason",
         "basketball_nba_summer_league"],
    )
    def test_every_season_variant_on_production_wants_its_parent(self, key):
        """The three variant rows `sports` actually holds (#4945's census)."""
        assert wants_parent_league_row(key) is True

    @pytest.mark.parametrize(
        "key",
        ["baseball_mlb", "americanfootball_nfl", "basketball_nba",
         "icehockey_nhl", "tennis_atp", None, ""],
    )
    def test_a_canonical_row_never_defers(self, key):
        """The other direction, and the one that keeps the page fast.

        A non-variant team must take this branch in a string test and issue no
        query at all — `test_a_canonical_team_page_issues_no_extra_query` is the
        route-level half of the same claim.
        """
        assert wants_parent_league_row(key) is False

    def test_a_bare_suffix_is_not_a_variant(self):
        """`"_preseason"` has no parent to defer to, so it is not a variant.

        Pinned here as well as in `is_season_variant` because this module is
        where a caller would meet the consequence: a key that IS its own suffix
        would collapse under `league_identity` to the empty string and could
        match anything.
        """
        assert wants_parent_league_row("_preseason") is False
        assert wants_parent_league_row("_summer_league") is False


# ===========================================================================
# choose_parent_league_row — the pick, and every way it declines
# ===========================================================================


class TestChooseParentLeagueRow:
    def test_the_red_sox_case_returns_the_league_row(self):
        assert choose_parent_league_row(
            "baseball_mlb_preseason", [(RED_SOX_PARENT, "baseball_mlb")]
        ) == RED_SOX_PARENT

    def test_a_canonical_subject_declines_even_with_a_perfect_candidate(self):
        """CONTROL. `baseball_mlb` is already the row a reader should get.

        The candidate here is a LEAGUE row, not a variant one, and that is the
        whole point: a variant candidate is thrown out by the not-a-variant
        filter, so a subject-side test built on one passes with the
        `is_season_variant` subject guard DELETED. Measured — that mutant
        survived the first cut of this suite. With a league candidate the guard
        is the only thing returning `None`, and deleting it bounces a real MLB
        page onto the other row sharing its `espn_id`.
        """
        assert choose_parent_league_row(
            "baseball_mlb", [(CARDINALS_PARENT_B, "baseball_mlb")]
        ) is None

    def test_a_variant_subject_with_that_same_candidate_is_chosen(self):
        """The other direction of the guard above: same candidate, variant
        subject, and now it IS the answer. Without this pair the `None` above
        could come from anything."""
        assert choose_parent_league_row(
            "baseball_mlb_preseason", [(CARDINALS_PARENT_B, "baseball_mlb")]
        ) == CARDINALS_PARENT_B

    def test_no_candidate_declines(self):
        """The NFL/NBA path: their variant rows carry no `espn_id`, so the
        caller's query returns nothing and the page is served unchanged."""
        assert choose_parent_league_row("baseball_mlb_preseason", []) is None

    def test_two_candidates_decline_rather_than_guess(self):
        """The Cardinals. `espn_id=24` maps to TWO `baseball_mlb` rows.

        Declining is the ship: #1798 owns which of the two is the club. A rule
        that broke the tie here on a content hunch would be a second matcher
        deciding an identity question.
        """
        assert choose_parent_league_row(
            "baseball_mlb_preseason",
            [(CARDINALS_PARENT_A, "baseball_mlb"), (CARDINALS_PARENT_B, "baseball_mlb")],
        ) is None

    def test_one_of_the_two_cardinals_rows_alone_would_be_chosen(self):
        """The other direction of the ambiguity test.

        Without this, `test_two_candidates_decline_rather_than_guess` passes
        against a function that declines for EVERY Cardinals-shaped input — the
        ambiguity would not be what produced the `None`.
        """
        assert choose_parent_league_row(
            "baseball_mlb_preseason", [(CARDINALS_PARENT_A, "baseball_mlb")]
        ) == CARDINALS_PARENT_A

    def test_a_candidate_in_another_league_is_not_the_club(self):
        """ESPN team ids are scoped PER LEAGUE, so `espn_id=2` is the Red Sox in
        MLB and somebody else entirely in the NBA. The caller's query is keyed on
        the id alone, so this filter is the only thing standing between a reader
        and another sport's club."""
        assert choose_parent_league_row(
            "baseball_mlb_preseason",
            [(4242, "basketball_nba"), (5151, "americanfootball_nfl")],
        ) is None

    def test_the_right_league_is_picked_out_of_a_cross_league_collision(self):
        """Same input plus the real sibling: exactly one survives the filter."""
        assert choose_parent_league_row(
            "baseball_mlb_preseason",
            [(4242, "basketball_nba"), (RED_SOX_PARENT, "baseball_mlb"), (5151, "icehockey_nhl")],
        ) == RED_SOX_PARENT

    def test_a_second_variant_is_never_the_parent(self):
        """A variant defers to the PARENT, never sideways to another variant —
        otherwise two variant rows could point at each other and a reader would
        get whichever the query happened to return first."""
        assert choose_parent_league_row(
            "baseball_mlb_preseason",
            [(999, "baseball_mlb_preseason")],
        ) is None

    def test_a_none_key_on_a_candidate_is_skipped_not_crashed(self):
        """`teams.sport_id` is nullable, so a candidate can arrive keyless."""
        assert choose_parent_league_row(
            "baseball_mlb_preseason",
            [(999, None), (RED_SOX_PARENT, "baseball_mlb")],
        ) == RED_SOX_PARENT


# ===========================================================================
# The route — what a reader actually gets
# ===========================================================================


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.first.return_value = items[0] if items else None
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    result.all.return_value = items
    result.first.return_value = items[0] if items else None
    return result


def _team(*, team_id, slug, sport_key, record, espn_id, standings=None, name="Boston Red Sox"):
    return SimpleNamespace(
        id=team_id,
        slug=slug,
        name=name,
        abbreviation="BOS",
        location="Boston",
        sport=SimpleNamespace(id=1, key=sport_key, name=sport_key),
        espn_id=espn_id,
        primary_color="#BD3039",
        secondary_color="#0C2340",
        logo_url_small="https://example.test/bos-sm.png",
        logo_url_large="https://example.test/bos-lg.png",
        current_record=record,
        standings_data=standings,
        season_stats=None,
        roster_players=[],
    )


SPRING_ROW = dict(
    team_id=RED_SOX_VARIANT, slug="boston-red-sox",
    sport_key="baseball_mlb_preseason", record="13-15", espn_id="2", standings=None,
)
LEAGUE_ROW = dict(
    team_id=RED_SOX_PARENT, slug="boston-red-sox-mlb",
    sport_key="baseball_mlb", record="80-67", espn_id="2",
    standings={"wins": 80, "losses": 67, "division": "East", "div_rank": 2},
)

# upcoming, recent, futures, championship — the four the route runs after resolve.
_EMPTY_TAIL = [_scalars_result([]) for _ in range(4)]


def _long_tail(n=12):
    """Padding, so StopIteration is never what a call-count test measures."""
    return [_scalars_result([]) for _ in range(n)]


class TestTeamRouteServesTheLeagueRow:
    async def test_the_spring_slug_now_serves_the_pennant_race(self, client, mock_db):
        mock_db.execute.side_effect = [
            _scalars_result([_team(**SPRING_ROW)]),          # slug lookup → 853
            _scalars_result([(RED_SOX_PARENT, "baseball_mlb")]),  # siblings on espn_id
            _scalars_result([_team(**LEAGUE_ROW)]),          # load the parent
            *_EMPTY_TAIL,
        ]

        resp = await client.get("/api/teams/boston-red-sox")
        assert resp.status_code == 200
        team = resp.json()["team"]
        assert team["id"] == RED_SOX_PARENT
        assert team["record"] == "80-67"
        # The breadcrumb reads off this key — acceptance item 1 of #2498.
        assert team["sport_key"] == "baseball_mlb"
        # And the division the spring row could never carry.
        assert team["standings"]["division"] == "East"

    async def test_the_cardinals_shape_is_served_unchanged(self, client, mock_db):
        """CONTROL, end to end. Two league rows share the id, so the route keeps
        what it found rather than picking. The page stays wrong until #1798 —
        deliberately, and the test says so."""
        mock_db.execute.side_effect = [
            _scalars_result([_team(**SPRING_ROW)]),
            _scalars_result([
                (CARDINALS_PARENT_A, "baseball_mlb"),
                (CARDINALS_PARENT_B, "baseball_mlb"),
            ]),
            *_EMPTY_TAIL,
        ]

        resp = await client.get("/api/teams/boston-red-sox")
        assert resp.status_code == 200
        team = resp.json()["team"]
        assert team["id"] == RED_SOX_VARIANT
        assert team["record"] == "13-15"

    async def test_the_swap_costs_two_queries_and_a_canonical_page_pays_zero(
        self, client, mock_db
    ):
        """CONTROL, counted rather than inferred.

        The first cut of this test asserted "no extra query" by handing the route
        EXACTLY the results it used to need and trusting a sixth `db.execute` to
        StopIteration. It did not: the tail is not always fully consumed, so
        there was slack and the mutant that ran the sibling query on EVERY team
        page passed. `call_count` has no slack. Both requests end on the same
        league row, so everything downstream of the resolve is identical and the
        difference is exactly the two queries this change adds.
        """
        league = _team(**LEAGUE_ROW)
        mock_db.execute.side_effect = [_scalars_result([league]), *_long_tail()]
        canonical = await client.get("/api/teams/boston-red-sox-mlb")
        assert canonical.status_code == 200
        baseline = mock_db.execute.call_count

        mock_db.execute.side_effect = [
            _scalars_result([_team(**SPRING_ROW)]),
            _scalars_result([(RED_SOX_PARENT, "baseball_mlb")]),
            _scalars_result([_team(**LEAGUE_ROW)]),
            *_long_tail(),
        ]
        swapped_at = mock_db.execute.call_count
        variant = await client.get("/api/teams/boston-red-sox")
        assert variant.status_code == 200
        assert variant.json()["team"]["id"] == RED_SOX_PARENT

        assert baseline >= 1, "the canonical request issued no queries at all"
        assert mock_db.execute.call_count - swapped_at == baseline + 2

    async def test_a_variant_row_with_no_espn_id_pays_nothing(self, client, mock_db):
        """CONTROL, and it is the whole of the NFL and NBA populations: 32
        `americanfootball_nfl_preseason` and 29 `basketball_nba_summer_league`
        rows carry no `espn_id`, so the gate's second clause stops them before
        any query. Counted against a canonical request for the same reason as
        above."""
        mock_db.execute.side_effect = [_scalars_result([_team(**LEAGUE_ROW)]), *_long_tail()]
        assert (await client.get("/api/teams/boston-red-sox-mlb")).status_code == 200
        baseline = mock_db.execute.call_count

        chargers = _team(
            team_id=17736, slug="los-angeles-chargers-preseason",
            sport_key="americanfootball_nfl_preseason", record="1-2",
            espn_id=None, name="Los Angeles Chargers",
        )
        mock_db.execute.side_effect = [_scalars_result([chargers]), *_long_tail()]
        before = mock_db.execute.call_count
        resp = await client.get("/api/teams/los-angeles-chargers-preseason")
        assert resp.status_code == 200
        assert resp.json()["team"]["id"] == 17736
        assert mock_db.execute.call_count - before == baseline

    async def test_a_parent_that_vanishes_between_queries_serves_the_variant(
        self, client, mock_db
    ):
        """A worse page beats no page. If the chosen row cannot be loaded the
        route keeps the one it has rather than 404-ing a page that was serving a
        moment ago."""
        mock_db.execute.side_effect = [
            _scalars_result([_team(**SPRING_ROW)]),
            _scalars_result([(RED_SOX_PARENT, "baseball_mlb")]),
            _scalars_result([]),  # the parent row is gone
            *_EMPTY_TAIL,
        ]

        resp = await client.get("/api/teams/boston-red-sox")
        assert resp.status_code == 200
        assert resp.json()["team"]["id"] == RED_SOX_VARIANT
