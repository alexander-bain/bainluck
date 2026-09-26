"""#8628 — a search page shows one row per O/U ladder, not one per rung.

Production 2026-09-25 (v5051): `?q=united` served 9 of 10 market rows as rungs of
`Scunthorpe United FC vs. Hartlepool United FC`, and `?q=rangers` headed its
ANSWERS card with three rungs of `Carrick Rangers O/U`. The fixtures are those
production rows, verbatim (id, source, name, market_tier).
"""

from __future__ import annotations

import pytest

from app.routes import events as events_route


class _Market:
    def __init__(self, id, name, source="polymarket", market_tier=5):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None


GC = "Glentoran FC vs. Carrick Rangers"
CARRICK_RUNGS = [
    _Market(61848492, f"{GC}: Carrick Rangers O/U 0.5"),
    _Market(61848493, f"{GC}: Carrick Rangers O/U 1.5"),
    _Market(62065280, f"{GC}: Carrick Rangers O/U 2.5"),
    _Market(62065281, f"{GC}: Carrick Rangers O/U 3.5"),
    _Market(62065282, f"{GC}: Carrick Rangers O/U 4.5"),
]
GC_MAIN = _Market(61844253, GC)
GC_EXACT = _Market(61844262, f"{GC} - Exact Score")
GLENTORAN_O05 = _Market(61911839, f"{GC}: Glentoran FC O/U 0.5")
GC_TOTAL_O05 = _Market(62025082, f"{GC}: O/U 0.5")
GC_TOTAL_O85 = _Market(61911837, f"{GC}: O/U 8.5")
GC_1H_O05 = _Market(62025089, f"{GC}: 1st Half O/U 0.5")
GC_CORNERS_95 = _Market(62322715, f"{GC}: O/U 9.5 Total Corners")
GC_CORNERS_105 = _Market(62322716, f"{GC}: O/U 10.5 Total Corners")

SH = "Scunthorpe United FC vs. Hartlepool United FC"
# The served `?q=united` page, in its served order.
UNITED_PAGE = [
    _Market(13492442, "46th FIDE Chess Olympiad Open Tournament Winner", market_tier=1),
    _Market(62322202, f"{SH}: Scunthorpe United FC O/U 5.5 Corners"),
    _Market(62322203, f"{SH}: Hartlepool United FC O/U 4.5 Corners"),
    _Market(61823335, f"{SH}: Scunthorpe United FC O/U 1.5"),
    _Market(61823336, f"{SH}: Scunthorpe United FC O/U 2.5"),
    _Market(61823337, f"{SH}: Hartlepool United FC O/U 0.5"),
    _Market(61823338, f"{SH}: Hartlepool United FC O/U 1.5"),
    _Market(62303936, "Manchester United WFC vs. West Ham United FC: Manchester United WFC O/U 2.5"),
    _Market(62303937, "Manchester United WFC vs. West Ham United FC: West Ham United FC O/U 0.5"),
    _Market(61823351, f"{SH}: Scunthorpe United FC O/U 3.5"),
]


def _page(rows):
    """Run rows through the route's own per-row decision, in order."""
    seen: set = set()
    kept: dict = {}
    return [m.id for m in rows if events_route._admit_search_future(m, seen, kept, [])]


def test_precondition_the_old_keys_keep_every_rung_apart():
    """Without this the tests below could pass on the old rule and prove nothing."""
    keys = {events_route._normalize_futures_dedup_key(m) for m in CARRICK_RUNGS}
    assert len(keys) == len(CARRICK_RUNGS)
    assert len({events_route._search_question_identity(m)[0] for m in CARRICK_RUNGS}) == 5


def test_the_rangers_specimen_ladder_prints_once():
    assert _page(CARRICK_RUNGS) == [CARRICK_RUNGS[0].id]


def test_the_first_rung_the_ranking_hands_in_is_the_one_kept():
    rungs = list(reversed(CARRICK_RUNGS))
    assert _page(rungs) == [rungs[0].id]


def test_the_united_specimen_page_keeps_one_row_per_ladder():
    kept = _page(UNITED_PAGE)
    assert kept == [
        13492442,  # not a rung
        62322202,  # Scunthorpe corners
        62322203,  # Hartlepool corners
        61823335,  # Scunthorpe goals (2.5 and 3.5 fold into it)
        61823337,  # Hartlepool goals (1.5 folds into it)
        62303936,  # Manchester United WFC goals
        62303937,  # West Ham goals
    ]


def test_the_matchs_other_questions_keep_their_rows():
    rows = [GC_MAIN, GC_EXACT, CARRICK_RUNGS[0], GLENTORAN_O05, GC_TOTAL_O05, GC_1H_O05,
            GC_CORNERS_95]
    assert _page(rows) == [m.id for m in rows]


@pytest.mark.parametrize(
    "a, b",
    [(GC_TOTAL_O05, GC_TOTAL_O85), (GC_CORNERS_95, GC_CORNERS_105)],
    ids=["one-digit-lines", "two-digit-line"],
)
def test_rungs_of_one_ladder_fold_whatever_the_line(a, b):
    assert _page([a, b]) == [a.id]


def test_a_number_outside_the_line_still_separates_two_rows():
    a = _Market(1, "Game 1: Aaron Judge Total Bases O/U 1.5")
    b = _Market(2, "Game 2: Aaron Judge Total Bases O/U 1.5")
    assert _page([a, b]) == [1, 2]


def test_a_row_with_no_line_is_not_a_rung():
    for m in (GC_MAIN, GC_EXACT, _Market(3, "NHL: NYR Rangers Total Points")):
        assert events_route._search_ladder_key(m) is None


def test_the_fold_survives_the_refill_loop_sharing_the_bookkeeping():
    """The window and the refill pass the SAME sets, so a rung the window kept
    cannot come back through the refill."""
    seen: set = set()
    kept: dict = {}
    window = [m for m in CARRICK_RUNGS[:2] if events_route._admit_search_future(m, seen, kept, [])]
    refill = [m for m in CARRICK_RUNGS[2:] if events_route._admit_search_future(m, seen, kept, [])]
    assert [m.id for m in window] == [CARRICK_RUNGS[0].id] and refill == []


def test_the_shared_tiered_key_is_unchanged():
    """`league_futures` reads the tiered key; #8628 must not move it."""
    assert events_route._normalize_futures_dedup_key(CARRICK_RUNGS[0]) == (
        "matchup:carrick rangers carrick rangers o u 0 5|glentoran fc:5"
    )
