"""#8689 r2 — a name that holds a multi-word query only as scattered word pieces yields.

`bainluck.com/search?q=us open` (production 2026-09-28 ~01:05Z, after r1's
word-start fix) served `US job openings in August` as futures row 2, above
`2027 US Open Women's Singles Winner` and `US Open Winner`. The reranker's
name-match test is a substring test, so "US ... open(ings)" passes it, and the
volume sort (714 against 41 and NULL) put the jobs question first. Fixture ids,
names and volumes are the production rows read the same minute.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes import events as events_route

STAMP = datetime.now(timezone.utc) - timedelta(hours=5)


class _Outcome:
    def __init__(self, id, name, p):
        self.id = id
        self.name = name
        self.current_probability = p
        self.last_updated = STAMP


class _Market:
    def __init__(self, id, name, volume, category="tennis", market_tier=1):
        self.id = id
        self.source = "kalshi"
        self.name = name
        self.market_tier = market_tier
        self.volume = volume
        # Contested legs, so #8726's decided-board partition never fires here.
        self.outcomes = [_Outcome(id * 10, "A", 0.55), _Outcome(id * 10 + 1, "B", 0.45)]
        self.canonical_market_key = None
        self.external_id = None
        self.llm_sport_category = category
        self.sport = None


HONEY = (60207194, "Number of Honey Deuces sold at the US Open", 101179)
MENS = (61308736, "2027 US Open Men's Singles Winner", 917)
JOBS = (60481225, "US job openings in August", 714)
WOMENS = (61064200, "2027 US Open Women's Singles Winner", 41)
GOLF = (7, "US Open Winner", None)


def _us_open_rows():
    return [
        _Market(*HONEY),
        _Market(*MENS),
        _Market(*JOBS, category="economics", market_tier=2),
        _Market(*WOMENS),
        _Market(*GOLF, category="golf"),
    ]


def _ids(rows):
    return [m.id for m in rows]


def _rank(rows, query):
    return events_route._rerank_search_futures(rows, query)


US_OPEN = [("us", None), ("open", None)]


def test_precondition_the_jobs_row_is_a_name_match_that_wins_the_volume_sort():
    jobs = _Market(*JOBS)
    assert events_route._query_name_match(jobs, US_OPEN)
    assert jobs.volume > WOMENS[2]
    # The volume sort alone reproduces the production page: jobs at 3 of 5
    # (production served the Men's row as an event, so jobs read as futures 2).
    by_volume = sorted(_us_open_rows(), key=events_route._market_volume, reverse=True)
    assert _ids(by_volume)[2] == JOBS[0]


def test_us_open_puts_the_jobs_question_below_every_us_open_market():
    assert _ids(_rank(_us_open_rows(), US_OPEN)) == [
        HONEY[0], MENS[0], WOMENS[0], GOLF[0], JOBS[0],
    ]


def test_typing_us_ope_already_holds_the_order():
    ranked = _rank(_us_open_rows(), [("us", None), ("ope", None)])
    assert _ids(ranked)[-1] == JOBS[0]
    assert _ids(ranked)[:2] == [HONEY[0], MENS[0]]


def test_the_jobs_row_still_leads_where_it_is_the_only_kind_of_row():
    # Nothing is dropped: a page of loose rows only keeps its volume order.
    rows = [_Market(*JOBS), _Market(1, "Openings in the US labor market", 5)]
    assert _ids(_rank(rows, US_OPEN)) == [JOBS[0], 1]


def test_a_single_word_query_is_untouched():
    # "reopen" holds `open` only mid-word; one word is r1's job, not this rule's.
    rows = [_Market(1, "Will the mall reopen by May?", 900), _Market(2, "US Open Winner", 10)]
    assert _ids(_rank(rows, [("open", None)])) == [1, 2]


@pytest.mark.parametrize(
    "query, rows",
    [
        # Terms apart but whole words: the main markets keep their volume lead.
        (
            [("nba", None), ("champion", "winner")],
            [(1, "NBA: 2027 Champion", 9000), (2, "2027 NBA Champion", 500),
             (3, "9th Straight Different NBA Champion", 100)],
        ),
        (
            [("fed", "federal reserve"), ("rate", None)],
            [(1, "Fed funds rate after Dec 2026 meeting?", 9000),
             (2, "Another Fed rate hike in 2026?", 500)],
        ),
        # A plural inside a phrase is still a phrase.
        (
            [("grand", None), ("prix", None)],
            [(1, "Will Lando Norris win 3+ Grands Prix in 2026?", 9000),
             (2, "Rain during the Azerbaijan Grand Prix?", 500)],
        ),
        # An apostrophe, straight or curly, never splits the match.
        (
            [("ballon", None), ("d'or", None)],
            [(1, "Ballon d'Or 2026: Top 3 Finishers", 9000),
             (2, "Will Harry Kane win the Ballon d’Or?", 500)],
        ),
        # A multi-word expansion counts as the term.
        (
            [("la", "los angeles"), ("lakers", None)],
            [(1, "Los Angeles Lakers Win Total", 9000), (2, "LA Lakers vs Suns", 500)],
        ),
    ],
)
def test_controls_whose_names_hold_the_query_tightly_keep_their_order(query, rows):
    markets = [_Market(i, n, v) for i, n, v in rows]
    assert _ids(_rank(markets, query)) == [i for i, _, _ in rows]


def test_finish_top_3_sinks_the_finishers_boards_the_named_second_page_move():
    # The one other page the rule moved in the 57-query read. "Finishers" holds
    # `finish` only as a word piece, away from "top 3"; the player rows hold all
    # three as whole words. The top row keeps first place.
    query = [("finish", None), ("top", None), ("3", None)]
    rows = [
        _Market(1, "Ballon d'Or Top 3 Finish 2026", 9000),
        _Market(2, "SEC Regular Season: Top 3 Finishers", 800),
        _Market(3, "Will Harry Kane finish in the top 3 of the 2026 Ballon d'Or?", 50),
    ]
    assert _ids(_rank(rows, query)) == [1, 3, 2]


def test_outcome_only_rows_stay_below_every_name_match():
    outcome_only = _Market(9, "2026 Tennis Awards", 10**7)
    ranked = _rank(_us_open_rows() + [outcome_only], US_OPEN)
    assert _ids(ranked)[-2:] == [JOBS[0], 9]
