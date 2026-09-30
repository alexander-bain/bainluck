"""#9865 — `world series` leads with baseball's boards, not a Dota 2 namesake.

Production, MLB postseason, `GET /api/events/typeahead?q=world series`:

    2026-09-28 16:05Z  row 2  Dota 2: … - EPL World Series …  Match Winner 17%
    2026-09-30 16:05Z  row 2  Dota 2: Ivory vs Team Kinetix (BO3) - EPL World
                              Series Southeast Asia Group Stage   (esports, tier 4)
                       row 3  MLB 2026: World Series Winning League   (tier 1)
                       row 4  MLB Postseason: World Series MVP        (tier 3)

Every row names both words, so the reranker's name-match split ties them and its
volume sort decides: the Dota board carries volume 22,272 and the two MLB boards
carry NULL. No team resolves for `world series`, so `_demote_wrong_sport` had no
sport to arm on. The bare championship name now supplies it.

This file pins the helper and the shared reranker on the production rows; the
real-Postgres route gate (`integration/test_typeahead_world_series_sport_pg_9865.py`)
proves the dropdown asks it.
"""

from types import SimpleNamespace

from app.routes.events import (
    _championship_query_sport_category,
    _rerank_search_futures,
    expand_search_terms,
)


def _exp(q: str):
    return expand_search_terms(q.split())


def _market(name: str, category: str | None, volume, tier: int):
    return SimpleNamespace(
        name=name,
        outcomes=[],
        llm_sport_category=category,
        market_tier=tier,
        volume=volume,
        volume_24h=None,
        external_id=None,
        source="polymarket",
        resolution_date=None,
        status="open",
    )


# The production rows, read 2026-09-30 16:1xZ (id, name, category, volume, tier).
CHAMPION = _market("MLB World Series Champion 2026", "baseball", 42291678, 1)
DOTA = _market(
    "Dota 2: Ivory vs Team Kinetix (BO3) - EPL World Series Southeast Asia Group Stage",
    "esports", 22272, 4,
)
LEAGUE = _market("MLB 2026: World Series Winning League", "baseball", None, 1)
MVP = _market("MLB Postseason: World Series MVP", "baseball", None, 3)
POKER = _market("World Series of Poker Main Event Winner", "poker", 900000, 5)
UNCLAIMED = _market("World Series ratings above 15M?", None, 50000, 5)


def _names(rows):
    return [m.name for m in rows]


class TestTheHelper:
    def test_the_bare_name_is_baseball(self):
        assert _championship_query_sport_category(_exp("world series")) == "baseball"
        assert _championship_query_sport_category(_exp("World Series")) == "baseball"

    def test_its_own_league_word_keeps_it(self):
        assert _championship_query_sport_category(_exp("mlb world series")) == "baseball"

    def test_any_other_word_is_another_question(self):
        for q in (
            "world series of poker",
            "nfl world series",
            "dodgers world series",
            "world series mvp",
        ):
            assert _championship_query_sport_category(_exp(q)) is None, q

    def test_half_the_name_is_nothing(self):
        for q in ("world", "series", "world cup", "super bowl", "trump"):
            assert _championship_query_sport_category(_exp(q)) is None, q


class TestTheSharedReranker:
    def test_the_dota_board_no_longer_leads_the_mlb_boards(self):
        got = _names(_rerank_search_futures([CHAMPION, DOTA, LEAGUE, MVP], _exp("world series")))
        assert got.index(DOTA.name) == 3, got
        assert got[:3] == [CHAMPION.name, LEAGUE.name, MVP.name], got

    def test_the_dota_board_is_kept_not_dropped(self):
        got = _names(_rerank_search_futures([DOTA, LEAGUE], _exp("world series")))
        assert got == [LEAGUE.name, DOTA.name], got

    def test_without_the_phrase_the_order_is_what_production_served(self, monkeypatch):
        # Anti-vacuity: sever the helper and the reranker is the old one — the
        # volume sort puts the Dota board second, above both NULL-volume boards.
        monkeypatch.setattr(
            "app.routes.events._championship_query_sport_category", lambda _e: None
        )
        got = _names(_rerank_search_futures([CHAMPION, DOTA, LEAGUE, MVP], _exp("world series")))
        assert got[:2] == [CHAMPION.name, DOTA.name], got

    def test_a_row_with_no_sport_claim_keeps_its_place(self):
        # FAIL-OPEN, as `_demote_wrong_sport` is: NULL category is no claim.
        got = _names(_rerank_search_futures([UNCLAIMED, LEAGUE], _exp("world series")))
        assert got == [UNCLAIMED.name, LEAGUE.name], got

    def test_poker_asked_for_by_name_is_untouched(self):
        got = _names(
            _rerank_search_futures([CHAMPION, POKER], _exp("world series of poker"))
        )
        assert got[0] == POKER.name, got

    def test_the_callers_own_sport_still_wins(self):
        # A resolved sport from the caller is never overridden by the phrase.
        got = _names(
            _rerank_search_futures([CHAMPION, DOTA], _exp("world series"), "esports")
        )
        assert got[0] == DOTA.name, got
