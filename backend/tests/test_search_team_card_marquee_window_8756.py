"""#8756 — searching `eagles` shows the Philadelphia Eagles on the teams card.

Production 2026-09-26 ~00:55Z, `/search?q=eagles`: the card read American,
Coppin St, Morehead St, Marquette and Southern Mississippi — no Philadelphia
Eagles — while `/typeahead` for the same word led with them. Two stacked causes,
both read from production:

* the teams window is `ts_rank_cd` then `Team.name`, LIMIT 25. The rank counts
  how often the word appears across name + aliases: six college rows score 4.5,
  Philadelphia 3.0 tied with 19 more, and "Philadelphia" sorted to row 26. It was
  never FETCHED.
* inside the window the card capped at 5 by that same count, BEFORE the
  match-class scorer (ruling 041) — which ranks an NFL club owning the alias
  "Eagles" first — ever saw it.

The route arm (both causes, a strawman reproducing the defect, and a text-first
control) is in `tests/integration/test_search_recall_contract.py`, which needs a
real Postgres. These pin what is checkable without one.
"""

import inspect
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.utils.search_match_class import rank


def _code_lines(fn) -> str:
    """The function's source with comment lines dropped — the comments quote the
    code they replaced, so a raw substring check would match the explanation."""
    return "\n".join(
        line for line in inspect.getsource(fn).splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_sql_marquee_order_is_the_python_one():
    """The window's tiebreak and `_sort_matched_team_rows`' tiebreak must name the
    same leagues, or the fetch keeps a row the sort would not have preferred."""
    sql = str(
        ev._team_marquee_order().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    for key in ev._MARQUEE_TEAM_SPORT_KEYS:
        assert f"'{key}'" in sql, (key, sql)
    assert "basketball_ncaab" not in sql
    assert ev._team_marquee_rank("americanfootball_nfl") == 0
    assert ev._team_marquee_rank("basketball_ncaab") == 1


def test_the_window_breaks_rank_ties_on_marquee_before_name():
    src = _code_lines(ev.search_events)
    assert ".order_by(team_rank.desc(), _team_marquee_order(), Team.name)" in src
    assert ".order_by(team_rank.desc(), Team.name)" not in src


def test_the_card_is_capped_by_the_scorer_not_before_it():
    src = _code_lines(ev.search_events)
    assert "len(matched_teams) >= 5" not in src
    ranked = src.index("matched_teams = _search_rank_candidates(")
    world_cup = src.index('"soccer_fifa_world_cup" in sports_found')
    payload = src.index('"teams": matched_teams,')
    # Ranked before the World Cup check reads the card, and exactly once.
    assert ranked < world_cup < payload
    assert src.count("_search_team_evidence(t), t) for t in matched_teams") == 1


def _team(name, sport_key, aliases, team_rank):
    return SimpleNamespace(
        name=name, sport_key=sport_key, alternate_names=aliases, team_rank=team_rank,
    )


# Production's window for `eagles` after the fix, top rows (2026-09-26).
EAGLES_WINDOW = [
    _team("American Eagles", "basketball_ncaab",
          ["Eagles", "American", "American University Eagles"], 4.5),
    _team("Coppin St Eagles", "basketball_wncaab",
          ["Eagles", "Coppin St", "Coppin State Eagles"], 4.5),
    _team("Marquette Golden Eagles", "lacrosse_ncaa",
          ["Golden Eagles", "Marquette", "Marquette Golden Eagles"], 4.5),
    _team("Morehead St Eagles", "baseball_ncaa",
          ["Morehead State Eagles", "Eagles", "Morehead St"], 4.5),
    _team("Southern Mississippi Golden Eagles", "americanfootball_ncaaf",
          ["Golden Eagles", "Southern Miss Golden Eagles", "Southern Miss"], 4.5),
    _team("Philadelphia Eagles", "americanfootball_nfl", ["Eagles"], 3.0),
    _team("Boston College Eagles", "basketball_ncaab", ["Eagles", "Boston College"], 3.0),
]


def _card(rows, cap_first: bool) -> list[str]:
    ordered = ev._pick_team_row_per_name(ev._sort_matched_team_rows(rows))
    teams = [
        {"name": r.name, "abbreviation": None, "sport_key": r.sport_key,
         "_aliases": list(r.alternate_names)}
        for r in ordered
    ]
    if cap_first:
        teams = teams[:5]
    return [t["name"] for t in rank("eagles", [(ev._search_team_evidence(t), t) for t in teams])[:5]]


def test_the_scorer_over_the_whole_window_puts_philadelphia_first():
    assert _card(EAGLES_WINDOW, cap_first=False)[0] == "Philadelphia Eagles"


def test_capping_before_the_scorer_loses_philadelphia():
    """Strawman: the old order of operations reproduces what production served."""
    assert "Philadelphia Eagles" not in _card(EAGLES_WINDOW, cap_first=True)
