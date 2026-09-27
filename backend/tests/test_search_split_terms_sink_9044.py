"""#9044 — a club typed in words sinks games its words reach only split across sides.

`oregon state` on production 2026-09-27 04:0xZ: the second game card was Ohio
State Buckeyes vs Oregon Ducks and 4 of 8 were Ducks games — `oregon` landed on
one side, `state` on the other, and neither side was the club the reader named.

The behaviour is proven on a real Postgres in
`tests/integration/test_search_split_terms_sink_pg_9044.py` (strawman and
matchup control included). This file pins the helper's arming and the wiring.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import _split_terms_order_key

NCAAF = "americanfootball_ncaaf"


def _row(name, sport_key=NCAAF, rank=0.1, aliases=()):
    """A team-window row: the columns `_team_card_keyed` builds the card from."""
    return SimpleNamespace(
        id=hash((name, sport_key)) % 10_000, name=name, slug=None,
        abbreviation=None, logo_url_small=None, current_record=None,
        alternate_names=list(aliases), sport_key=sport_key, team_rank=rank,
    )


# What the teams bucket holds for `oregon state` (and neighbours).
TEAMS = [
    _row("Oregon State Beavers", rank=0.3),
    _row("Oregon Ducks"),
    _row("Ohio State Buckeyes"),
    _row("Oklahoma State Cowboys"),
]


def _exp(*terms):
    return [(t, None) for t in terms]


def _sql(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestArming:
    def test_a_club_typed_in_two_words_arms_it(self):
        assert _split_terms_order_key(TEAMS, "oregon state", _exp("oregon", "state")) is not None

    def test_one_word_never_arms_it(self):
        """No split is possible, and `oregon` must keep today's SQL."""
        assert _split_terms_order_key(TEAMS, "oregon", _exp("oregon")) is None

    def test_a_matchup_query_does_not_arm_it(self):
        """`ohio state oregon`: no club owns all three words — the reader named two."""
        assert (
            _split_terms_order_key(TEAMS, "ohio state oregon", _exp("ohio", "state", "oregon"))
            is None
        )

    def test_no_teams_card_does_not_arm_it(self):
        assert _split_terms_order_key([], "oregon state", _exp("oregon", "state")) is None
        assert _split_terms_order_key(None, "oregon state", _exp("oregon", "state")) is None

    def test_a_leader_that_owns_only_some_words_does_not_arm_it(self):
        """`oregon ducks state`: the card's leader misses a word, so it is no club."""
        assert (
            _split_terms_order_key(TEAMS, "oregon ducks state", _exp("oregon", "ducks", "state"))
            is None
        )

    def test_productions_leader_arms_it_through_its_alias(self):
        """Production's card led with the NCAAB row `Oregon St Beavers`, whose
        `alternate_names` carry "Oregon State Beavers" (teams 1079, 2026-09-27)."""
        rows = [
            _row("Oregon St Beavers", "basketball_ncaab", rank=0.3,
                 aliases=("Oregon State Beavers", "Oregon St", "Beavers")),
            _row("Oregon State Beavers", rank=0.3, aliases=("Beavers", "Oregon St")),
            _row("Oregon Ducks"),
        ]
        assert _split_terms_order_key(rows, "oregon state", _exp("oregon", "state")) is not None

    def test_an_alias_owning_the_words_arms_it(self):
        """MC0 on an alias counts: `man city` IS Manchester City."""
        rows = [_row("Manchester City", "soccer_epl", aliases=("Man City",))]
        assert _split_terms_order_key(rows, "man city", _exp("man", "city")) is not None


class TestTheKey:
    def test_every_word_on_one_side_is_zero_else_one(self):
        sql = _sql(_split_terms_order_key(TEAMS, "oregon state", _exp("oregon", "state")))
        # `%%`: the psycopg dialect escapes a literal percent when binding inline.
        assert sql == (
            "CASE WHEN (events.home_team_name ILIKE '%%oregon%%' AND "
            "events.home_team_name ILIKE '%%state%%' OR "
            "events.away_team_name ILIKE '%%oregon%%' AND "
            "events.away_team_name ILIKE '%%state%%') THEN 0 ELSE 1 END"
        ), sql

    def test_a_synonym_expansion_counts_on_its_side(self):
        """Same per-term test as the recall (`_build_expanded_ilike`)."""
        rows = [_row("Oregon State Beavers")]
        sql = _sql(
            _split_terms_order_key(rows, "oregon state", [("oregon", None), ("state", "st")])
        )
        assert (
            "(events.home_team_name ILIKE '%%state%%' OR "
            "events.home_team_name ILIKE '%%st%%')"
        ) in sql, sql


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_built_from_the_teams_window_and_the_recall_terms(self):
        assert (
            "_split_terms_key = _split_terms_order_key(_early_team_rows, _q_identity, expanded)"
            in self.SRC
        )

    def test_it_sits_above_the_status_tier_below_a_named_day(self):
        start = self.SRC.index("_day_boost = _intent_day_order_key(_intent, now)")
        block = self.SRC[start:start + 1800]
        day = block.index("*( (_day_boost,) if _day_boost is not None else () ),")
        teamless = block.index(
            "*( (_teamless_sport_key,) if _teamless_sport_key is not None else () ),"
        )
        split = block.index(
            "*( (_split_terms_key,) if _split_terms_key is not None else () ),"
        )
        status = block.index("status_order,")
        assert day < teamless < split < status
