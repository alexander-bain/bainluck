"""#4811 — a write-dead `conf_rank` must never reach a client.

`tasks/statpal_sync.py` is the only writer of `standings_data` and has not
emitted `conf_rank` since #4732, so every surviving value is a division place
wearing a conference label. 13 production rows still carry one; five produce a
repeated (conference, rank) pair, and one of those pairs — Columbus and Ottawa,
both Eastern Conference #5 — is two genuinely different clubs, so no dedupe
reaches it.

Every fixture here starts WITH `conf_rank` set and asserts a sibling key
survives. A test that only asserted "the key is absent" would pass against a
fixture that never had it, and would also pass against a serializer that
dropped the standings blob entirely.
"""

from types import SimpleNamespace

import pytest

from app.utils.standings_shape import WRITE_DEAD_STANDINGS_KEYS, public_standings


# The shape of the 13 frozen production rows: pre-#4732 `conf_rank`, no
# `div_rank`, and in five cases a rank another team also claims.
STALE_ROW = {
    "conference": "Eastern Conference",
    "conf_rank": 5,
    "wins": 38,
    "losses": 24,
}

# The shape every row the writer has touched since #4732 carries.
FRESH_ROW = {
    "conference": "Eastern Conference",
    "division": "Metropolitan",
    "div_rank": 5,
    "wins": 38,
    "losses": 24,
}


class TestPublicStandings:
    def test_drops_conf_rank_and_keeps_its_siblings(self):
        out = public_standings(STALE_ROW)
        assert "conf_rank" not in out
        # Not vacuous: the blob is still served, minus one key.
        assert out["conference"] == "Eastern Conference"
        assert out["wins"] == 38
        assert out["losses"] == 24

    def test_does_not_mutate_the_caller_s_dict(self):
        # These are live SQLAlchemy JSONB values; mutating one in place is the
        # silent-write failure of gotcha #4.
        row = dict(STALE_ROW)
        public_standings(row)
        assert row["conf_rank"] == 5

    def test_a_fresh_row_is_returned_untouched_and_uncopied(self):
        out = public_standings(FRESH_ROW)
        assert out is FRESH_ROW
        assert out["div_rank"] == 5

    def test_div_rank_survives_when_both_are_present(self):
        # No production row has both today, but the rule must not be "keep
        # whichever rank happens to be first".
        both = {**FRESH_ROW, "conf_rank": 9}
        out = public_standings(both)
        assert "conf_rank" not in out
        assert out["div_rank"] == 5

    @pytest.mark.parametrize("value", [None, [], "", 0, [{"conf_rank": 1}]])
    def test_non_dict_values_pass_through(self, value):
        assert public_standings(value) is value or public_standings(value) == value

    def test_conf_rank_is_actually_in_the_dead_list(self):
        # Guards the inverse mistake: emptying the tuple would make every test
        # above pass except this one.
        assert "conf_rank" in WRITE_DEAD_STANDINGS_KEYS


class TestServingBoundaries:
    """The two places a standings blob leaves the server."""

    def _team(self, standings):
        return SimpleNamespace(
            id=572,
            slug="columbus-nhl",
            name="Columbus",
            abbreviation="CBJ",
            location="Columbus",
            primary_color="002654",
            secondary_color="ce1126",
            logo_url_small="s.png",
            logo_url_large="l.png",
            logo_url="l.png",
            current_record="38-24-11",
            standings_data=standings,
            season_stats=None,
            roster_players=None,
            sport=SimpleNamespace(key="icehockey_nhl", name="NHL"),
        )

    def test_team_page_payload_drops_it(self):
        from app.routes.teams import _format_team

        out = _format_team(self._team(dict(STALE_ROW)))
        assert "conf_rank" not in out["standings"]
        # The hero still has something to print.
        assert out["standings"]["conference"] == "Eastern Conference"
        assert out["record"] == "38-24-11"

    def test_event_team_card_payload_drops_it(self):
        from app.routes.events import _format_team_data

        out = _format_team_data(self._team(dict(STALE_ROW)))
        assert "conf_rank" not in out["standings"]
        assert out["standings"]["conference"] == "Eastern Conference"

    def test_event_team_card_still_serves_a_fresh_rank(self):
        from app.routes.events import _format_team_data

        out = _format_team_data(self._team(dict(FRESH_ROW)))
        assert out["standings"]["div_rank"] == 5


class TestStandingsContext:
    def test_context_does_not_print_a_conference_rank_from_conf_rank(self):
        from app.routes.events import _compute_standings_context

        home = SimpleNamespace(standings_data=dict(STALE_ROW))
        ctx = _compute_standings_context(home, None, "Columbus", "Ottawa")
        # The record still renders — so this is not "the function returned None".
        assert ctx is not None
        assert "38-24" in ctx["home"]
        assert "#5" not in ctx["home"]
        assert "Eastern Conference" not in ctx["home"]

    def test_context_still_prints_a_fresh_division_rank(self):
        from app.routes.events import _compute_standings_context

        home = SimpleNamespace(standings_data=dict(FRESH_ROW))
        ctx = _compute_standings_context(home, None, "Columbus", "Ottawa")
        assert "#5 Metropolitan" in ctx["home"]

    def test_top_seed_stakes_ignores_conf_rank(self):
        from app.routes.events import _compute_standings_context

        # Both rows look like "#1 and #2 in the conference" under the old key.
        # With `conf_rank` write-dead and no `league_rank`, there is no
        # top-seed claim to make.
        home = SimpleNamespace(standings_data={"conf_rank": 1, "wins": 60, "losses": 22})
        away = SimpleNamespace(standings_data={"conf_rank": 2, "wins": 45, "losses": 37})
        ctx = _compute_standings_context(home, away, "Detroit", "Orlando")
        assert ctx is not None
        assert ctx.get("stakes") != "Top seed matchup"

    def test_top_seed_stakes_still_fires_on_league_rank(self):
        from app.routes.events import _compute_standings_context

        home = SimpleNamespace(standings_data={"league_rank": 1, "wins": 60, "losses": 22})
        away = SimpleNamespace(standings_data={"league_rank": 2, "wins": 45, "losses": 37})
        ctx = _compute_standings_context(home, away, "Detroit", "Orlando")
        assert ctx["stakes"] == "Top seed matchup"
