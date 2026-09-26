"""#8942 — a club query's games read in date order; the tag tier is for the rest.

The behaviour (the club's next game leads, the no-card control still takes the
tier, nothing dropped) is proven on a real Postgres in
`tests/integration/test_search_club_schedule_date_order_pg_8942.py`. This file
pins the helper's contract and the wiring into every games ORDER BY.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import _search_tag_boost, _search_tag_boost_keys


def _row(name, sport_key, rank=0.1):
    """A team-window row: the columns `_team_card_keyed` builds the card from."""
    return SimpleNamespace(
        id=hash((name, sport_key)) % 10_000, name=name, slug=None,
        abbreviation=None, logo_url_small=None, current_record=None,
        alternate_names=[], sport_key=sport_key, team_rank=rank,
    )


def _sql(expr) -> str:
    return str(
        expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


class TestTheHelper:
    def test_a_club_card_drops_the_tier(self):
        """`arsenal` on production: the card is Arsenal (+ Arsenal Tivat)."""
        rows = [_row("Arsenal", "soccer_epl"), _row("Arsenal Tivat", "soccer_other")]
        assert _search_tag_boost_keys(rows, "arsenal") == ()

    def test_one_club_is_enough(self):
        assert _search_tag_boost_keys([_row("Liverpool", "soccer_epl")], "liverpool") == ()

    def test_no_card_keeps_the_tier(self):
        keys = _search_tag_boost_keys([], "nfl")
        assert len(keys) == 1
        assert _sql(keys[0]) == _sql(_search_tag_boost())

    def test_no_rows_read_keeps_the_tier(self):
        """A shed teams read hands the route `[]` (or None) — no card, no change."""
        assert len(_search_tag_boost_keys(None, "arsenal")) == 1

    def test_an_individual_sport_row_is_not_a_club(self):
        """Tennis/golf rows never make the card, so a player query keeps the tier."""
        rows = [_row("Carlos Alcaraz", "tennis_atp")]
        assert len(_search_tag_boost_keys(rows, "alcaraz")) == 1


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_the_keys_read_the_early_team_rows(self):
        read = self.SRC.index("_early_team_rows = (await db.execute(_search_team_rows_q([]))).all()")
        keys = self.SRC.index("tag_boost_keys = _search_tag_boost_keys(_early_team_rows, _q_identity)")
        assert read < keys

    def test_every_games_order_by_takes_the_keys(self):
        """Primary, bridge and resolved-team arms — a bare tier left in one of
        them would reorder a club's schedule on that arm only."""
        assert self.SRC.count("*tag_boost_keys,") == 3
        assert "        tag_boost,\n" not in self.SRC
        assert "_search_tag_boost()" not in self.SRC
