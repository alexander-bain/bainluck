"""#9578 — a postseason word reaches the games of every round in progress.

No database. Production 2026-09-29, the first day of MLB's postseason:
`mlb playoffs`, `playoffs`, `mlb postseason` and `baseball playoffs` served
ZERO games while `wild card` served the day's four Wild Card games. The route
half (both screens, real Postgres) is `integration/test_search_postseason_round_pg.py`.
"""

from app.routes.events import (
    _POSTSEASON_ROUND_ALIASES,
    _resolve_postseason_games,
    _resolve_postseason_round,
)

MLB_ROUNDS = [r for r in dict.fromkeys(_POSTSEASON_ROUND_ALIASES.values()) if r[0] == "baseball_mlb"]


def test_the_round_map_has_an_mlb_round():
    assert MLB_ROUNDS, "the round map lost its MLB round; every assertion below would be vacuous"


def test_a_postseason_word_names_every_round_in_progress():
    for terms in (
        ["playoffs"], ["Playoffs"], ["playoff"], ["postseason"],
        ["mlb", "playoffs"], ["MLB", "Playoffs"], ["mlb", "postseason"],
        ["baseball", "playoffs"],
    ):
        rounds, consumed = _resolve_postseason_games(terms)
        assert rounds == MLB_ROUNDS, terms
        assert consumed and consumed <= {"playoffs", "playoff", "postseason"}, (terms, consumed)


def test_another_leagues_or_one_clubs_postseason_gets_no_round():
    for terms in (
        ["nfl", "playoffs"], ["nba", "playoffs"], ["nhl", "postseason"],
        ["patriots", "playoffs"], ["lazio", "playoffs"], ["stanley", "cup", "playoffs"],
    ):
        assert _resolve_postseason_games(terms) == ([], set()), terms


def test_a_round_name_is_still_only_its_own_round():
    for terms in (["wild", "card"], ["wildcard"], ["mlb", "wild", "card"]):
        rnd, consumed = _resolve_postseason_round(terms)
        assert _resolve_postseason_games(terms) == ([rnd], consumed), terms


def test_queries_without_a_postseason_word_are_untouched():
    for terms in (["mlb"], ["yankees"], ["wild"], ["play"], ["post", "season"], []):
        assert _resolve_postseason_games(terms) == ([], set()), terms


def test_the_round_scope_adds_no_table_to_the_statement_it_joins():
    """The zero-result bridge reads the recall arms with no `sports` join.

    The scope used to put `Sport.key == …` beside its `IN`, which named the
    outer `sports` and made that statement `events × sports`.
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.routes.events import _postseason_round_event_scope

    for rnd in MLB_ROUNDS:
        stmt = select(Event.id).where(_postseason_round_event_scope(rnd))
        assert [f.name for f in stmt.get_final_froms()] == ["events"]
