"""#8524 — `/hub/esports` prop cards said "Games Total: O/U 4.5" and nothing else.

Seen on production 2026-09-25 03:10Z at 390px (lane1b/610): PROPS drew
"Map 2 Total Rounds: Over/Under 21.5" and "Games Total: O/U 4.5", chipped SERIES
PROP, with no team, match or date on the card. The rows, from `/api/hub/esports`:

    62250557  Games Total: O/U 4.5                   polymarket:1075925
    61993448  Map 3 Total Rounds: Over/Under 19.5    polymarket:1004178

and the match name lived only on the group's grouped row, measured the same
hour with db-query:

    60748103  championship  event_title = "Valorant: Karmine Corp vs XLG Gaming
                                           (BO3) - VCT Champions Group D"
    61779741  game_prop     (no event_title)         <- every leg, the same

The fixtures below are those rows. What must NOT move is pinned beside what must:
a match-group row that already names both sides, and a non-match group whose rows
are complete questions ("Will Paul Skenes be on the cover of MLB The Show 27?").
"""

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import hub as hub_module
from app.utils.hub_prop_matchup import (
    attach_group_matchups,
    groups_needing_a_matchup,
    names_a_matchup,
)

KC_XLG = "polymarket:1004178"
KC_XLG_TITLE = "Valorant: Karmine Corp vs XLG Gaming (BO3) - VCT Champions Group D"
GAMES_TOTAL = "polymarket:1075925"
GAMES_TOTAL_TITLE = "Counter-Strike: GamerLegion vs K27 (BO3) - 1win Private Club #1 Playoffs"
COVER = "polymarket:502899"
COVER_TITLE = "MLB The Show 27 cover athlete?"


def _prop(market_id, name, group_id, **extra):
    """One PROPS card in the shape `/api/hub/esports` served it (priced, so
    `build_hub`'s UX-P181 filter keeps it)."""
    return {
        "id": market_id,
        "name": name,
        "source": "polymarket",
        "market_tier": 5,
        "category": "game_prop",
        "group_id": group_id,
        "section": "props",
        "prop_type": "series prop",
        "outcome_count": 2,
        "top_outcomes": [
            {"name": "Over", "probability": 0.52},
            {"name": "Under", "probability": 0.48},
        ],
        **extra,
    }


def _props():
    return [
        _prop(61993448, "Map 3 Total Rounds: Over/Under 19.5", KC_XLG),
        _prop(62250557, "Games Total: O/U 4.5", GAMES_TOTAL),
        _prop(61901396, "Map Handicap: KC (-1.5) vs XLG Gaming (+1.5)", KC_XLG),
        _prop(24014907, "Will Paul Skenes be on the cover of MLB The Show 27?", COVER),
        _prop(1, "Total Kills O/U 20.5", None),
    ]


TITLES = {KC_XLG: KC_XLG_TITLE, GAMES_TOTAL: GAMES_TOTAL_TITLE, COVER: COVER_TITLE}


class TestTheRule:
    def test_the_matchless_props_borrow_their_match(self):
        rows = attach_group_matchups({"props": _props()}, TITLES)["props"]
        by_id = {r["id"]: r for r in rows}
        assert by_id[61993448]["event_title"] == KC_XLG_TITLE
        assert by_id[62250557]["event_title"] == GAMES_TOTAL_TITLE

    def test_before_the_fix_those_cards_named_no_match(self):
        """The strawman: the served rows carried no field naming the match."""
        for row in _props()[:2]:
            assert not names_a_matchup(row["name"])
            assert "event_title" not in row and not row.get("competition")

    def test_a_row_that_already_names_both_sides_is_left_alone(self):
        rows = attach_group_matchups({"props": _props()}, TITLES)["props"]
        handicap = next(r for r in rows if r["id"] == 61901396)
        assert "event_title" not in handicap

    def test_a_group_that_is_not_a_match_lends_nothing(self):
        rows = attach_group_matchups({"props": _props()}, TITLES)["props"]
        cover = next(r for r in rows if r["id"] == 24014907)
        assert "event_title" not in cover

    def test_a_row_with_no_group_or_no_stored_title_is_unchanged(self):
        props = _props()
        rows = attach_group_matchups({"props": props}, {KC_XLG: KC_XLG_TITLE})["props"]
        assert rows[1] == props[1]  # GAMES_TOTAL: no title read
        assert rows[4] == props[4]  # no group_id

    def test_only_the_groups_that_could_borrow_are_queried(self):
        assert groups_needing_a_matchup({"props": _props()}) == {
            KC_XLG,
            GAMES_TOTAL,
            COVER,
        }

    def test_neither_the_mapping_nor_its_rows_are_mutated(self):
        props = _props()
        before = [dict(r) for r in props]
        attach_group_matchups({"props": props}, TITLES)
        assert props == before

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("TYLOO vs Team Liquid", True),
            ("TYLOO vs. Team Liquid", True),
            ("TYLOO VS Team Liquid", True),
            ("Games Total: O/U 4.5", False),
            ("Canvas versus nothing", False),
            (None, False),
        ],
    )
    def test_names_a_matchup(self, text, expected):
        assert names_a_matchup(text) is expected


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(self.rows)


class TestTheRead:
    async def test_first_titled_row_per_group_wins_and_blanks_are_skipped(self):
        db = _Db(
            [
                (KC_XLG, "   "),
                (KC_XLG, KC_XLG_TITLE),
                (KC_XLG, "a later, different title"),
                (GAMES_TOTAL, GAMES_TOTAL_TITLE),
            ]
        )
        titles = await hub_module.fetch_group_event_titles(db, {KC_XLG, GAMES_TOTAL})
        assert titles == {KC_XLG: KC_XLG_TITLE, GAMES_TOTAL: GAMES_TOTAL_TITLE}

    async def test_the_query_reads_event_title_by_group_in_id_order(self):
        db = _Db([])
        await hub_module.fetch_group_event_titles(db, {KC_XLG})
        sql = str(
            db.statements[0].compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        assert "market_metadata ->> 'event_title'" in sql
        assert "futures_markets.group_id IN ('polymarket:1004178')" in sql
        assert "ORDER BY futures_markets.group_id, futures_markets.id" in sql

    async def test_nothing_to_ask_asks_nothing(self):
        db = _Db([])
        assert await hub_module.fetch_group_event_titles(db, set()) == {}
        assert db.statements == []


class TestThePayload:
    """On the payload `build_hub` actually serves."""

    async def _hub(self, monkeypatch, fetch):
        async def _league(sport_key, db):
            return {"sections": {"props": _props()}}

        async def _no_matches(*args, **kwargs):
            return []

        monkeypatch.setattr(hub_module, "get_league_futures", _league)
        monkeypatch.setattr(hub_module, "build_linked_matches", _no_matches)
        monkeypatch.setattr(hub_module, "fetch_group_event_titles", fetch)
        return await hub_module.build_hub(hub_module.HUB_CONFIGS["esports"], db=None)

    async def test_the_esports_props_name_their_match(self, monkeypatch):
        async def _fetch(db, group_ids):
            return {g: TITLES[g] for g in group_ids if g in TITLES}

        payload = await self._hub(monkeypatch, _fetch)
        titled = {
            r["name"]: r.get("event_title") for r in payload["sections"]["props"]
        }
        assert titled["Games Total: O/U 4.5"] == GAMES_TOTAL_TITLE
        assert titled["Map 3 Total Rounds: Over/Under 19.5"] == KC_XLG_TITLE
        assert titled["Map Handicap: KC (-1.5) vs XLG Gaming (+1.5)"] is None

    async def test_a_failed_read_leaves_every_card_as_it_was(self, monkeypatch):
        async def _boom(db, group_ids):
            raise RuntimeError("db down")

        payload = await self._hub(monkeypatch, _boom)
        rows = payload["sections"]["props"]
        assert len(rows) == len(_props())
        assert all("event_title" not in r for r in rows)
